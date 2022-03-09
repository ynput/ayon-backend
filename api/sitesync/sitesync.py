import os

from fastapi import APIRouter, Depends, Query, Path, Response

from openpype.access.utils import folder_access_list
from openpype.api import dep_project_name, dep_current_user, dep_representation_id
from openpype.entities.user import UserEntity
from openpype.entities.representation import RepresentationEntity
from openpype.lib.postgres import Postgres
from openpype.utils import SQLTool, json_loads, json_dumps, EntityID

from .models import (
    StatusEnum,
    SortByEnum,
    SiteSyncParamsModel,
    SiteSyncSummaryItem,
    SiteSyncSummaryModel,
    RepresentationStateModel,
    FileModel,
    SyncStatusModel,
)

router = APIRouter(tags=["Site sync"])


def get_overal_status(files: dict) -> StatusEnum:
    all_states = [v.get("status", StatusEnum.NOT_AVAILABLE) for v in files.values()]
    if all(stat == StatusEnum.NOT_AVAILABLE for stat in all_states):
        return StatusEnum.NOT_AVAILABLE
    elif all(stat == StatusEnum.SYNCED for stat in all_states):
        return StatusEnum.SYNCED
    elif any(stat == StatusEnum.FAILED for stat in all_states):
        return StatusEnum.FAILED
    elif any(stat == StatusEnum.IN_PROGRESS for stat in all_states):
        return StatusEnum.IN_PROGRESS
    elif any(stat == StatusEnum.PAUSED for stat in all_states):
        return StatusEnum.PAUSED
    elif all(stat == StatusEnum.QUEUED for stat in all_states):
        return StatusEnum.QUEUED
    return StatusEnum.NOT_AVAILABLE


#
# GET SITE SYNC PARAMS
#


@router.get(
    "/projects/{project_name}/sitesync/params",
    response_model=SiteSyncParamsModel,
)
async def get_site_sync_params(
    project_name: str = Depends(dep_project_name),
    user: UserEntity = Depends(dep_current_user),
) -> SiteSyncParamsModel:

    access_list = await folder_access_list(user, project_name, "read")
    conditions = []
    if access_list is not None:
        conditions.append(f"h.path like ANY ('{{ {','.join(access_list)} }}')")

    query = f"""
        SELECT
            DISTINCT(r.name) as name,
            COUNT (*) OVER () as total_count
        FROM project_{project_name}.representations as r
        INNER JOIN project_{project_name}.versions as v
            ON r.version_id = v.id
        INNER JOIN project_{project_name}.subsets as s
            ON v.subset_id = s.id
        INNER JOIN project_{project_name}.hierarchy as h
            ON s.folder_id = h.id
        {SQLTool.conditions(conditions)}
    """

    total_count = 0
    names = []
    async for row in Postgres.iterate(query):
        total_count = row["total_count"] or 0
        names.append(row["name"])

    return SiteSyncParamsModel(count=total_count, names=names)


#
# GET SITE SYNC OVERAL STATE
#


@router.get(
    "/projects/{project_name}/sitesync/state",
    response_model=SiteSyncSummaryModel,
)
async def get_site_sync_state(
    project_name: str = Depends(dep_project_name),
    user: UserEntity = Depends(dep_current_user),
    localSite: str = Query(
        ...,
        description="Name of the local site",
        example="Machine42",
    ),
    remoteSite: str = Query(
        ...,
        description="Name of the remote site",
        example="GDrive",
    ),
    sortBy: SortByEnum = Query(
        SortByEnum.folder,
        description="Sort the result by this value",
        example=SortByEnum.folder,
    ),
    sortDesc: bool = Query(
        False,
        name="Sort descending",
        description="Sort the result in descending order",
    ),
    folderFilter: str
    | None = Query(
        None,
        description="Filter folders by name",
        example="sh042",
    ),
    subsetFilter: str
    | None = Query(
        None,
        description="Filter subsets by name",
        example="animation",
    ),
    localStatusFilter: list[StatusEnum]
    | None = Query(
        None,
        description=f"List of states to show. Available options: {StatusEnum.__doc__}",
        example=[StatusEnum.QUEUED, StatusEnum.IN_PROGRESS],
    ),
    remoteStatusFilter: list[StatusEnum]
    | None = Query(
        None,
        description=f"List of states to show. Available options: {StatusEnum.__doc__}",
        example=[StatusEnum.QUEUED, StatusEnum.IN_PROGRESS],
    ),
    nameFilter: list[str] | None = Query(None),
    representationId: str
    | None = Query(None, description="Select only the given representation."),
    # Pagination
    page: int = Query(1, ge=1),
    pageLength: int = Query(50, ge=1),
) -> SiteSyncSummaryModel:
    """Return a site sync state.

    When a representationId is provided,
    the result will contain only one representation,
    along with the information on individual files.
    """

    conditions = []

    if representationId is not None:
        conditions.append(f"r.id = '{representationId}'")

    else:
        # When a single representation is requested
        # We ignore the rest of the filter
        if folderFilter:
            conditions.append(f"f.name ILIKE '%{folderFilter}%'")

        if subsetFilter:
            conditions.append(f"s.name ILIKE '%{subsetFilter}%'")

        if localStatusFilter:
            statusFilter = [str(s.value) for s in localStatusFilter]
            conditions.append(f"local.status IN ({','.join(statusFilter)})")

        if remoteStatusFilter:
            statusFilter = [str(s.value) for s in remoteStatusFilter]
            conditions.append(f"remote.status IN {SQLTool.array(statusFilter)}")

        if nameFilter:
            conditions.append(f"r.name IN {SQLTool.array(nameFilter)}")

    access_list = await folder_access_list(user, project_name, "read")
    if access_list is not None:
        conditions.append(f"path like ANY ('{{ {','.join(access_list)} }}')")

    query = f"""
        SELECT
            f.name as folder,
            s.name as subset,
            v.version as version,
            r.name as representation,
            h.path as path,

            r.id as representation_id,
            r.data as represenation_data,
            local.data as local_data,
            remote.data as remote_data,
            local.status as localStatus,
            remote.status as remoteStatus
        FROM
            project_{project_name}.folders as f
        INNER JOIN
            project_{project_name}.subsets as s
            ON s.folder_id = f.id
        INNER JOIN
            project_{project_name}.versions as v
            ON v.subset_id = s.id
        INNER JOIN
            project_{project_name}.representations as r
            ON r.version_id = v.id
        INNER JOIN
            project_{project_name}.hierarchy as h
            ON f.id = h.id
        LEFT JOIN
            project_{project_name}.files as local
            ON local.representation_id = r.id
            AND local.site_name = '{localSite}'
        LEFT JOIN
            project_{project_name}.files as remote
            ON remote.representation_id = r.id
            AND remote.site_name = '{remoteSite}'

        {SQLTool.conditions(conditions)}

        ORDER BY {sortBy.value} {'DESC' if sortDesc else 'ASC'}
        LIMIT {pageLength}
        OFFSET { (page-1) * pageLength }
    """

    repres = []

    async for row in Postgres.iterate(query):
        rdata = json_loads(row["represenation_data"])
        files = rdata.get("files", {})
        file_count = len(files)
        total_size = sum([f.get("size") for f in files.values()])

        ldata = json_loads(row["local_data"] or "{}")
        lfiles = ldata.get("files", {})
        lsize = sum([f.get("size") for f in lfiles.values()] or [0])
        ltime = max([f.get("timestamp") for f in lfiles.values()] or [0])

        rdata = json_loads(row["remote_data"] or "{}")
        rfiles = ldata.get("files", {})
        rsize = sum([f.get("size") for f in rfiles.values()] or [0])
        rtime = max([f.get("timestamp") for f in rfiles.values()] or [0])

        local_status = SyncStatusModel(
            status=StatusEnum.NOT_AVAILABLE
            if row["localstatus"] is None
            else row["localstatus"],
            totalSize=total_size,
            size=lsize,
            timestamp=ltime,
        )
        remote_status = SyncStatusModel(
            status=StatusEnum.NOT_AVAILABLE
            if row["remotestatus"] is None
            else row["remotestatus"],
            totalSize=total_size,
            size=rsize,
            timestamp=rtime,
        )

        file_list = None
        if representationId:
            file_list = []
            for file_hash, file in files.items():

                local_file = lfiles.get(file_hash, {})
                remote_file = rfiles.get(file_hash, {})

                file_list.append(
                    FileModel(
                        fileHash=file_hash,
                        size=file["size"],
                        path=file["path"],
                        baseName=os.path.split(file["path"])[1],
                        localStatus=SyncStatusModel(
                            status=local_file.get("status", StatusEnum.NOT_AVAILABLE),
                            size=local_file.get("size", 0),
                            totalSize=file["size"],
                            timestamp=local_file.get("timestamp", 0),
                            message=local_file.get("message", None),
                            retries=local_file.get("retries", 0),
                        ),
                        remoteStatus=SyncStatusModel(
                            status=remote_file.get("status", StatusEnum.NOT_AVAILABLE),
                            size=remote_file.get("size", 0),
                            totalSize=file["size"],
                            timestamp=remote_file.get("timestamp", 0),
                            message=remote_file.get("message", None),
                            retries=remote_file.get("retries", 0),
                        ),
                    )
                )

        repres.append(
            SiteSyncSummaryItem.construct(
                folder=row["folder"],
                subset=row["subset"],
                version=row["version"],
                representation=row["representation"],
                representationId=EntityID.parse(row["representation_id"]),
                fileCount=file_count,
                size=total_size,
                localStatus=local_status,
                remoteStatus=remote_status,
                files=file_list,
            )
        )

    return SiteSyncSummaryModel(representations=repres)


#
# SET REPRESENTATION SYNC STATE
#


@router.post(
    "/projects/{project_name}/sitesync/state/{representation_id}/{site_name}",
    response_class=Response,
    status_code=204,
)
async def set_site_sync_representation_state(
    post_data: RepresentationStateModel,
    project_name: str = Depends(dep_project_name),
    user: UserEntity = Depends(dep_current_user),
    representation_id: str = Depends(dep_representation_id),
    site_name: str = Path(...),  # TODO: add regex validator/dependency here! Important!
) -> Response:

    priority = post_data.priority

    async with Postgres.acquire() as conn:
        async with conn.transaction():
            query = (
                f"""
                SELECT priority, data
                FROM project_{project_name}.files
                WHERE representation_id = $1 AND site_name = $2
                FOR UPDATE
                """,
                representation_id,
                site_name,
            )

            result = await conn.fetch(*query)
            do_insert = False
            if not result:
                do_insert = True
                repre = await RepresentationEntity.load(
                    project_name, representation_id, transaction=conn
                )
                files = {}
                for fhash, file in repre.data.get("files", {}).items():
                    files[fhash] = {
                        "hash": fhash,
                        "status": StatusEnum.NOT_AVAILABLE,
                        "size": 0,
                        "timestamp": 0,
                    }
            else:
                files = json_loads(result[0]["data"]).get("files")
                if priority is None:
                    priority = result[0]["priority"]

            for file in post_data.files:
                if file.fileHash not in files:
                    continue
                files[file.fileHash]["timestamp"] = file.timestamp
                files[file.fileHash]["status"] = file.status
                files[file.fileHash]["size"] = file.size

                if file.message:
                    files[file.fileHash]["message"] = file.message
                elif "message" in files[file.fileHash]:
                    del files[file.fileHash]["message"]

                if file.retries:
                    files[file.fileHash]["retries"] = file.retries
                elif "retries" in files[file.fileHash]:
                    del files[file.fileHash]["retries"]

            status = get_overal_status(files)

            if do_insert:
                await conn.execute(
                    f"""
                    INSERT INTO project_{project_name}.files
                    (representation_id, site_name, status, priority, data)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    representation_id,
                    site_name,
                    status,
                    post_data.priority if post_data.priority is not None else 50,
                    json_dumps({"files": files}),
                )
            else:
                await conn.execute(
                    f"""
                    UPDATE project_{project_name}.files
                    SET status = $1, data = $2, priority = $3
                    WHERE representation_id = $4 AND site_name = $5
                    """,
                    status,
                    json_dumps({"files": files}),
                    priority,
                    representation_id,
                    site_name,
                )

    return Response(status_code=204)

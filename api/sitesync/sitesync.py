from fastapi import APIRouter, Depends, Query, Path

from openpype.api import dep_project_name, dep_current_user
from openpype.entities.user import UserEntity
from openpype.lib.postgres import Postgres
from openpype.utils import SQLTool, json_loads, EntityID

from .models import (
    StatusEnum,
    SortByEnum,
    SiteSyncParamsModel,
    SiteSyncSummaryItem,
    SiteSyncSummaryModel,
    FileStatusModel,
)

router = APIRouter(
    tags=["Site sync"],
)


@router.get(
    "/projects/{project_name}/sitesync/params",
    response_model=SiteSyncParamsModel,
)
async def get_site_sync_params(
    project_name: str = Depends(dep_project_name),
    user: UserEntity = Depends(dep_current_user),
) -> SiteSyncParamsModel:

    # TODO: add folder_access conditions

    query = f"""
        SELECT
            DISTINCT(name) as name,
            COUNT (*) OVER () as total_count
        FROM project_{project_name}.representations
    """

    total_count = None
    names = []
    async for row in Postgres.iterate(query):
        total_count = row["total_count"]
        names.append(row["name"])

    return SiteSyncParamsModel(totalCount=total_count, names=names)


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
        description="Sort the result in descending order"
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
    statusFilter: list[StatusEnum]
    | None = Query(
        None,
        description=f"List of states to show. Available options: {StatusEnum.__doc__}",
        example=[StatusEnum.QUEUED, StatusEnum.IN_PROGRESS],
    ),
    # Pagination
    page: int = Query(1, ge=1),
    pageLength: int = Query(50, ge=1),
) -> SiteSyncSummaryModel:

    conditions = []

    if folderFilter:
        conditions.append(f"f.name ILIKE '{folderFilter}%'")

    if subsetFilter:
        conditions.append(f"s.name ILIKE '{subsetFilter}%'")

    if statusFilter:
        statusFilter = [str(s.value) for s in statusFilter]
        conditions.append(
            f"""
                local.status IN ({','.join(statusFilter)})
             OR remote.status IN ({','.join(statusFilter)})
            """
        )

    # TODO: add folder_access conditions

    query = f"""
        SELECT
            f.name as folder,
            s.name as subset,
            v.version as version,
            r.name as representation,

            r.id as representation_id,
            r.data as represenation_data,
            local.data as local_data,
            remote.data as remote_data,
            local.status as local_status,
            remote.status as remote_status

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

        repres.append(
            SiteSyncSummaryItem.construct(
                folder=row["folder"],
                subset=row["subset"],
                version=row["version"],
                representation=row["representation"],
                representationId=EntityID.parse(row["representation_id"]),
                fileCount=file_count,
                size=total_size,
                localSize=lsize,
                remoteSize=rsize,
                localTime=ltime,
                remoteTime=rtime,
                localStatus=row["local_status"] or StatusEnum.NOT_AVAILABLE,
                remoteStatus=row["remote_status"] or StatusEnum.NOT_AVAILABLE,
            )
        )

    return SiteSyncSummaryModel(
        representations=repres,
    )


@router.get(
    "/projects/{project_name}/sitesync/state/{representation_id}",
    response_model=list[FileStatusModel],
)
async def get_site_sync_representation_state(
    project_name: str = Depends(dep_project_name),
    user: UserEntity = Depends(dep_current_user),
    representation_id: str = Path(...),
    localSite: str = Query(..., description="Name of the local site"),
    remoteSite: str = Query(..., description="Name of the remote site"),
):
    ...


@router.post("/projects/{project_name}/sitesync/state/{representation_id}/{site_name}")
async def set_site_sync_representation_state(
    post_data: list[FileStatusModel],
    project_name: str = Depends(dep_project_name),
    user: UserEntity = Depends(dep_current_user),
    representation_id: str = Path(...),
    site_name: str = Path(...),
) -> list[FileStatusModel]:
    ...

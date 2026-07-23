from typing import Annotated, Any

from fastapi import Body, Query

from ayon_server.access.utils import folder_access_list
from ayon_server.api.dependencies import (
    AllowGuests,
    CurrentUser,
    FolderID,
    PathProjectLevelEntityType,
    ProductID,
    ProjectName,
    TaskID,
    VersionID,
)
from ayon_server.entities import (
    FolderEntity,
    ProductEntity,
    TaskEntity,
    UserEntity,
    VersionEntity,
)
from ayon_server.exceptions import BadRequestException, ForbiddenException
from ayon_server.graphql.resolvers.common import argdesc
from ayon_server.helpers.ffprobe import availability_from_media_info
from ayon_server.lib.postgres import Postgres
from ayon_server.reviewables.models import (
    ReviewableAuthor,
    ReviewableModel,
    ReviewableProcessingStatus,
)
from ayon_server.types import Field, OPModel

from .router import router


class ReviewablesRequestModel(OPModel):
    entity_ids: list[str] = Field(
        ...,
        description="List of target Entity IDs (folders, products, versions, etc.)"
        " to fetch reviewables for.",
    )


class VersionReviewablesModel(OPModel):
    id: str = Field(
        ..., title="Version ID", example="1a3b34ce-1b2c-4d5e-6f7a-8b9c0d1e2f3a"
    )
    name: str = Field(..., title="Version Name", example="v001")
    version: str = Field(..., title="Version Number", example=1)
    status: str = Field(..., title="Version Status", example="In Review")
    product_id: str = Field(
        ..., title="Product ID", example="1a3b34ce-1b2c-4d5e-6f7a-8b9c0d1e2f3a"
    )
    product_name: str = Field(..., title="Product Name", example="Product Name")
    product_type: str = Field(..., title="Product Type", example="Product Type")

    attrib: dict[str, Any] = Field(title="Version attributes", default_factory=dict)

    reviewables: list[ReviewableModel] = Field(
        default_factory=list,
        title="Reviewables",
        description="List of available reviewables",
    )


async def get_reviewables(
    project_name: str,
    *,
    version_id: str | None = None,
    version_ids: Annotated[
        list[str] | None, argdesc("List of parent version IDs to filter by")
    ] = None,
    product_id: str | None = None,
    product_ids: Annotated[
        list[str] | None, argdesc("List of products IDs to filter by")
    ] = None,
    task_id: str | None = None,
    task_ids: Annotated[
        list[str] | None, argdesc("List of tasks IDs to filter by")
    ] = None,
    folder_id: str | None = None,
    folder_ids: Annotated[
        list[str] | None, argdesc("List of folder IDs to filter by")
    ] = None,
    user: UserEntity | None = None,
    latest: Annotated[
        bool, Query(description="If True, returns only the latest version")
    ] = False,
    latest_done: Annotated[
        bool, Query(description="If True, returns only the latest approved versions")
    ] = False,
) -> list[VersionReviewablesModel]:
    cond = ""
    cval: str | list[str] | None = None
    if version_id:
        cond = "versions.id = $1"
        cval = version_id
    elif product_id:
        cond = "versions.product_id = $1"
        cval = product_id
    elif task_id:
        cond = "versions.task_id = $1"
        cval = task_id
    elif folder_id:
        cond = "products.folder_id = $1"
        cval = folder_id
    elif version_ids:
        cond = "versions.id = ANY($1::uuid[])"
        cval = version_ids
    elif product_ids:
        cond = "versions.product_id  = ANY($1::uuid[])"
        cval = product_ids
    elif task_ids:
        cond = "versions.task_id  = ANY($1::uuid[])"
        cval = task_ids
    elif folder_ids:
        cond = "products.folder_id  = ANY($1::uuid[])"
        cval = folder_ids

    access_list = None
    if user and not user.is_guest:
        try:
            access_list = await folder_access_list(user, project_name)
        except ForbiddenException:
            access_list = []

    if user and user.is_guest:
        cond += f""" AND versions.id IN (
            SELECT DISTINCT(i.entity_id) FROM
            project_{project_name}.entity_list_items i
            JOIN project_{project_name}.entity_lists l
                ON l.id = i.entity_list_id
                AND l.entity_list_type = 'review-session'
                AND (
                (l.access->'__guests__')::integer > 0
                OR (l.access->'guest:{user.attrib.email}')::integer > 0
            )
        )
        """

    if latest:
        cond += f"""AND versions.id IN (
                SELECT vv.id
                FROM project_{project_name}.versions vv
                WHERE vv.product_id = products.id
                ORDER BY vv.version DESC
                LIMIT 1
            )"""

    if latest_done:
        cond += f"""AND versions.id IN (
                SELECT vv.id
                FROM project_{project_name}.versions vv
                JOIN project_{project_name}.statuses st
                    ON st.name = vv.status
                WHERE vv.product_id = products.id
                    AND st.data->>'state' = 'done'
                ORDER BY vv.version DESC
                LIMIT 1
            )"""

    hierarchy_join = ""
    access_cond = ""
    if access_list is not None:
        access_list = [path.strip('"') for path in access_list]
        hierarchy_join = f"""
        JOIN
            project_{project_name}.hierarchy AS hierarchy
            ON hierarchy.id = products.folder_id
        """
        param_index = "$2" if cval is not None else "$1"
        access_cond = f"AND hierarchy.path LIKE ANY ({param_index}::text[])"

    query = f"""
        SELECT
            files.id as file_id,
            af.activity_id as activity_id,
            files.data as file_data,
            af.activity_data->>'reviewableLabel' AS label,
            af.activity_data->>'author' AS author_name,
            users.attrib->>'fullName' AS author_full_name,


            events.id AS event_id,
            events.status AS event_status,
            events.description AS event_description,

            versions.id AS version_id,
            versions.version AS version,
            versions.status AS version_status,
            versions.attrib AS version_attrib,
            products.name AS product_name,
            products.id AS product_id,
            products.product_type AS product_type,

            af.created_at,
            af.updated_at

        FROM
            project_{project_name}.versions AS versions
        JOIN
            project_{project_name}.products AS products
            ON products.id = versions.product_id
        {hierarchy_join}
        LEFT JOIN
            project_{project_name}.activity_feed af
            ON af.entity_id = versions.id
            AND af.entity_type = 'version'

        LEFT JOIN
            public.users AS users
            ON users.name = af.activity_data->>'author'

        LEFT JOIN
            project_{project_name}.files AS files
            ON files.activity_id = af.activity_id
            AND af.activity_type = 'reviewable'
            AND af.reference_type = 'origin'

        LEFT JOIN
            public.events AS events
            ON
                events.project_name = '{project_name}' AND
                events.topic = 'reviewable.process' AND
                events.created_at >= af.created_at AND
                (events.summary->>'sourceFileId')::UUID = files.id
        WHERE
            {cond}
            {access_cond}

        ORDER BY
            versions.version ASC,
            COALESCE(af.activity_data->>'reviewableOrder', '0')::integer ASC,
            af.creation_order ASC
    """

    processed: set[str] = set()
    versions: dict[str, VersionReviewablesModel] = {}
    query_params = (cval, access_list) if access_list is not None else (cval,)
    async for row in Postgres.iterate(query, *query_params):
        if row["version"] < 0:
            version_name = "HERO"
        else:
            version_name = f"v{row['version']:03d}"

        if row["version_id"] not in versions:
            attrib = row["version_attrib"] or {}
            if user and user.is_guest:
                # Remove all attributes for guest users
                attrib = {}
            elif user and not user.is_manager:
                perms = user.permissions(project_name)
                if perms.attrib_read.enabled:
                    for k in list(attrib.keys()):
                        if k in perms.attrib_read.attributes:
                            continue
                        attrib.pop(k, None)

            versions[row["version_id"]] = VersionReviewablesModel(
                id=row["version_id"],
                name=version_name,
                version=row["version"],
                status=row["version_status"],
                product_id=row["product_id"],
                product_name=row["product_name"],
                product_type=row["product_type"],
                attrib=attrib,
                reviewables=[],
            )

        if not row["file_id"]:
            continue

        file_data = row["file_data"] or {}
        media_info = file_data.get("mediaInfo", {})
        created_from = file_data.get("createdFrom")
        availability = availability_from_media_info(media_info)

        if created_from:
            processed.add(created_from)

        if availability in ["unknown", "ready"]:
            processing = None
        else:
            processing = None
            # if not await is_transcoder_available():
            #     processing = None
            # elif row["event_id"]:
            #     processing = ReviewableProcessingStatus(
            #         event_id=row["event_id"],
            #         status=row["event_status"],
            #         description=row["event_description"],
            #     )
            # else:
            #     processing = ReviewableProcessingStatus(
            #         event_id=None,
            #         status="enqueued",
            #         description="In a transcoder queue",
            #     )

        versions[row["version_id"]].reviewables.append(
            ReviewableModel(
                activity_id=row["activity_id"],
                availability=availability,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                created_from=created_from,
                file_id=row["file_id"],
                filename=file_data["filename"],
                label=row["label"],
                media_info=media_info,
                mimetype=file_data["mime"],
                processing=processing,
                author=ReviewableAuthor(
                    name=row["author_name"],
                    full_name=row["author_full_name"] or None,
                ),
            )
        )

    result = list(versions.values())
    for version in result:
        for reviewable in version.reviewables:
            if reviewable.file_id in processed and not reviewable.processing:
                reviewable.processing = ReviewableProcessingStatus(
                    event_id=None,
                    status="finished",
                    description="Processing finished",
                )

    return result


@router.get("/products/{product_id}/reviewables", dependencies=[AllowGuests])
async def get_reviewables_for_product(
    user: CurrentUser,
    project_name: ProjectName,
    product_id: ProductID,
    latest: Annotated[
        bool, Query(description="If True, returns only the latest version")
    ] = False,
    latest_done: Annotated[
        bool, Query(description="If True, returns only the latest approved versions")
    ] = False,
) -> list[VersionReviewablesModel]:
    """Returns a list of reviewables for a given product."""

    product = await ProductEntity.load(project_name, product_id)

    if not user.is_guest:
        await product.ensure_read_access(user)

    return await get_reviewables(
        project_name,
        product_id=product_id,
        user=user,
        latest=latest,
        latest_done=latest_done,
    )


@router.get("/versions/{version_id}/reviewables", dependencies=[AllowGuests])
async def get_reviewables_for_version(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    latest: Annotated[
        bool, Query(description="If True, returns only the latest version")
    ] = False,
    latest_done: Annotated[
        bool, Query(description="If True, returns only the latest approved versions")
    ] = False,
) -> VersionReviewablesModel:
    """Returns a list of reviewables for a given version."""

    version = await VersionEntity.load(project_name, version_id)

    if not user.is_guest:
        await version.ensure_read_access(user)

    return (
        await get_reviewables(
            project_name,
            version_id=version_id,
            user=user,
            latest=latest,
            latest_done=latest_done,
        )
    )[0]


@router.get("/tasks/{task_id}/reviewables", dependencies=[AllowGuests])
async def get_reviewables_for_task(
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
    latest: Annotated[
        bool, Query(description="If True, returns only the latest version")
    ] = False,
    latest_done: Annotated[
        bool, Query(description="If True, returns only the latest approved versions")
    ] = False,
) -> list[VersionReviewablesModel]:
    task = await TaskEntity.load(project_name, task_id)

    if not user.is_guest:
        await task.ensure_read_access(user)

    return await get_reviewables(
        project_name,
        task_id=task_id,
        user=user,
        latest=latest,
        latest_done=latest_done,
    )


@router.get("/folders/{folder_id}/reviewables", dependencies=[AllowGuests])
async def get_reviewables_for_folder(
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
    latest: Annotated[
        bool, Query(description="If True, returns only the latest version")
    ] = False,
    latest_done: Annotated[
        bool, Query(description="If True, returns only the latest approved versions")
    ] = False,
) -> list[VersionReviewablesModel]:
    folder = await FolderEntity.load(project_name, folder_id)

    if not user.is_guest:
        await folder.ensure_read_access(user)

    return await get_reviewables(
        project_name,
        folder_id=folder_id,
        user=user,
        latest=latest,
        latest_done=latest_done,
    )


@router.post("/{entity_type}/reviewables/list", dependencies=[AllowGuests])
async def get_reviewables_for_entities(
    user: CurrentUser,
    project_name: ProjectName,
    entity_type: PathProjectLevelEntityType,
    payload: Annotated[ReviewablesRequestModel, Body(...)],
    latest: Annotated[
        bool, Query(description="If True, returns only the latest version")
    ] = False,
    latest_done: Annotated[
        bool, Query(description="If True, returns only the latest approved versions")
    ] = False,
) -> list[VersionReviewablesModel]:
    """Fetches reviewables for a batch of entity IDs passed in the request."""

    supported_types = {"version", "product", "task", "folder"}
    if entity_type not in supported_types:
        raise BadRequestException(
            detail=f"Unsupported entity type for reviewables: {entity_type}"
        )

    kwargs: dict[str, Any] = {
        f"{entity_type}_ids": payload.entity_ids,
        "user": user,
        "latest": latest,
        "latest_done": latest_done,
    }

    return await get_reviewables(project_name, **kwargs)

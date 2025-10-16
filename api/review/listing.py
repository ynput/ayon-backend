from typing import Any

from ayon_server.api.dependencies import (
    AllowGuests,
    CurrentUser,
    FolderID,
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
from ayon_server.helpers.ffprobe import availability_from_media_info
from ayon_server.lib.postgres import Postgres
from ayon_server.reviewables.models import (
    ReviewableAuthor,
    ReviewableModel,
    ReviewableProcessingStatus,
)
from ayon_server.types import Field, OPModel

from .router import router


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
    product_id: str | None = None,
    task_id: str | None = None,
    folder_id: str | None = None,
    user: UserEntity | None = None,
) -> list[VersionReviewablesModel]:
    cond = ""
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

        ORDER BY
            versions.version ASC,
            COALESCE(af.activity_data->>'reviewableOrder', '0')::integer ASC,
            af.creation_order ASC
    """

    processed: set[str] = set()
    versions: dict[str, VersionReviewablesModel] = {}
    async for row in Postgres.iterate(query, cval):
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
) -> list[VersionReviewablesModel]:
    """Returns a list of reviewables for a given product."""

    product = await ProductEntity.load(project_name, product_id)

    if not user.is_guest:
        await product.ensure_read_access(user)

    return await get_reviewables(
        project_name,
        product_id=product_id,
        user=user,
    )


@router.get("/versions/{version_id}/reviewables", dependencies=[AllowGuests])
async def get_reviewables_for_version(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
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
        )
    )[0]


@router.get("/tasks/{task_id}/reviewables", dependencies=[AllowGuests])
async def get_reviewables_for_task(
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
) -> list[VersionReviewablesModel]:
    task = await TaskEntity.load(project_name, task_id)

    if not user.is_guest:
        await task.ensure_read_access(user)

    return await get_reviewables(
        project_name,
        task_id=task_id,
        user=user,
    )


@router.get("/folders/{folder_id}/reviewables", dependencies=[AllowGuests])
async def get_reviewables_for_folder(
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
) -> list[VersionReviewablesModel]:
    folder = await FolderEntity.load(project_name, folder_id)

    if not user.is_guest:
        await folder.ensure_read_access(user)

    return await get_reviewables(
        project_name,
        folder_id=folder_id,
        user=user,
    )

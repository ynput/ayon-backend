from ayon_server.api.dependencies import CurrentUser, ProductID, ProjectName, VersionID
from ayon_server.entities import ProductEntity, VersionEntity
from ayon_server.helpers.ffprobe import availability_from_media_info
from ayon_server.lib.postgres import Postgres

from .common import (
    ReviewableAuthor,
    ReviewableModel,
    ReviewableProcessingStatus,
    VersionReviewablesModel,
)
from .router import router


async def get_reviewables(
    project_name: str,
    version_id: str | None = None,
    product_id: str | None = None,
) -> list[VersionReviewablesModel]:
    if version_id:
        cond = "versions.id = $1"
        cval = version_id
    elif product_id:
        cond = "versions.product_id = $1"
        cval = product_id

    query = f"""
        SELECT
            files.id as file_id,
            af.activity_id as activity_id,
            files.data as file_data,
            af.activity_data->>'reviewableLabel' AS label,
            af.activity_data->>'author' AS author_name,
            users.attrib->>'fullName' AS author_full_name,


            events.id AS event_id,
            events.status AS status,
            events.description AS description,

            versions.id AS version_id,
            versions.version AS version,
            versions.status AS version_status,

            af.created_at,
            af.updated_at

        FROM
            project_{project_name}.versions AS versions
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
                events.topic = 'reviewable.processing' AND
                events.created_at >= af.created_at AND
                (events.summary->>'fileId')::UUID = files.id
        WHERE
            {cond}

        ORDER BY
            versions.version ASC,
            af.created_at ASC
    """

    versions: dict[str, VersionReviewablesModel] = {}
    async for row in Postgres.iterate(query, cval):
        if row["version"] < 0:
            version_name = "HERO"
        else:
            version_name = f"v{row['version']:03d}"

        if row["version_id"] not in versions:
            versions[row["version_id"]] = VersionReviewablesModel(
                id=row["version_id"],
                name=version_name,
                version=row["version"],
                status=row["version_status"],
                reviewables=[],
            )

        if not row["file_id"]:
            continue

        if row["event_id"]:
            processing = ReviewableProcessingStatus(
                event_id=row["event_id"],
                status=row["event_status"],
                description=row["event_description"],
            )
        else:
            processing = None

        file_data = row["file_data"] or {}
        media_info = file_data.get("mediaInfo", {})
        availability = availability_from_media_info(media_info)
        created_from = file_data.get("createdFrom")

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

    return list(versions.values())


@router.get("/products/{product_id}/reviewables")
async def get_reviewables_for_product(
    user: CurrentUser,
    project_name: ProjectName,
    product_id: ProductID,
) -> list[VersionReviewablesModel]:
    """Returns a list of reviewables for a given product."""

    product = await ProductEntity.load(project_name, product_id)
    await product.ensure_read_access(user)

    return await get_reviewables(project_name, product_id=product_id)


@router.get("/versions/{version_id}/reviewables")
async def get_reviewables_for_version(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
) -> VersionReviewablesModel:
    """Returns a list of reviewables for a given version."""

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_read_access(user)

    return (await get_reviewables(project_name, version_id=version_id))[0]

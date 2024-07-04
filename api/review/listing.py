from datetime import datetime
from typing import Any, Literal

from ayon_server.api.dependencies import CurrentUser, ProductID, ProjectName, VersionID
from ayon_server.entities import ProductEntity, VersionEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router

ReviewableAvailability = Literal["unknown", "needs_conversion", "ready"]


class ReviewableAuthor(OPModel):
    name: str = Field(..., title="Author Name")
    full_name: str | None = Field(None, title="Author Full Name")


class ReviewableProcessingStatus(OPModel):
    event_id: str = Field(..., title="Event ID")
    status: str = Field(..., title="Processing Status")
    description: str = Field(..., title="Processing Description")


class ReviewableModel(OPModel):
    file_id: str = Field(..., title="Reviewable ID")
    activity_id: str = Field(..., title="Activity ID")
    filename: str = Field(..., title="Reviewable Name")
    label: str | None = Field(None, title="Reviewable Label")
    mimetype: str = Field(..., title="Reviewable Mimetype")
    availability: ReviewableAvailability = Field(
        "unknown", title="Reviewable availability"
    )
    media_info: dict[str, Any] | None = Field(None, title="Media information")
    created_from: str | None = Field(None, title="File ID of the original file")
    processing: ReviewableProcessingStatus | None = Field(
        None,
        description="Information about the processing status",
    )
    created_at: datetime = Field(...)
    updated_at: datetime = Field(...)
    author: ReviewableAuthor = Field(..., title="Author Information")


class VersionReviewablesModel(OPModel):
    id: str = Field(
        ..., title="Version ID", example="1a3b34ce-1b2c-4d5e-6f7a-8b9c0d1e2f3a"
    )
    name: str = Field(..., title="Version Name", example="v001")
    version: str = Field(..., title="Version Number", example=1)
    status: str = Field(..., title="Version Status", example="In Review")

    reviewables: list[ReviewableModel] = Field(
        default_factory=list,
        title="Reviewables",
        description="List of available reviewables",
    )


COMPATIBILITY = {
    "codec": ["h264"],
    "pixelFormat": ["yuv420p"],
}


def availability_from_video_metadata(
    video_metadata: dict[str, Any],
) -> ReviewableAvailability:
    if not video_metadata:
        return "unknown"
    for key, values in COMPATIBILITY.items():
        if key not in video_metadata:
            return "unknown"
        if video_metadata[key] not in values:
            return "needs_conversion"
    return "ready"


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
        availability = availability_from_video_metadata(media_info)
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

from ayon_server.api.dependencies import CurrentUser, ProductID, ProjectName, VersionID
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router


class ReviewableModel(OPModel):
    file_id: str = Field(..., title="Reviewable ID")
    activity_id: str = Field(..., title="Activity ID")
    filename: str = Field(..., title="Reviewable Name")
    label: str | None = Field(None, title="Reviewable Label")
    mimetype: str = Field(..., title="Reviewable Mimetype")
    status: str = Field("ready", title="Reviewable Status")


class VersionReviewablesModel(OPModel):
    id: str = Field(..., title="Version ID")
    name: str = Field(..., title="Version Name")
    version: str = Field(..., title="Version Number")
    status: str = Field(..., title="Version Status")

    reviewables: list[ReviewableModel] = Field(
        default_factory=list, title="Reviewables"
    )


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
            files.data->>'mime' AS mimetype,
            files.data->>'filename' AS filename,
            files.data->>'label' AS label,

            versions.id AS version_id,
            versions.version AS version,
            versions.status AS version_status

        FROM
            project_{project_name}.files AS files
        JOIN
            project_{project_name}.activity_feed af
            ON files.activity_id = af.activity_id
            AND af.activity_type = 'reviewable'
            AND af.reference_type = 'origin'
        JOIN
            project_{project_name}.versions AS versions
            ON af.entity_id = versions.id
            AND af.entity_type = 'version'
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

        versions[row["version_id"]].reviewables.append(
            ReviewableModel(
                file_id=row["file_id"],
                activity_id=row["activity_id"],
                filename=row["filename"],
                label=row["label"],
                mimetype=row["mimetype"],
                status="ready",
            )
        )

    return list(versions.values())


@router.get("/products/{product_id}/reviewables")
async def list_reviewables_for_product(
    user: CurrentUser,
    project_name: ProjectName,
    product_id: ProductID,
) -> list[VersionReviewablesModel]:
    """Returns a list of reviewables for a given product."""

    return await get_reviewables(project_name, product_id=product_id)


@router.get("/versions/{version_id}/reviewables")
async def list_reviewables_for_version(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
) -> VersionReviewablesModel:
    return (await get_reviewables(project_name, version_id=version_id))[0]

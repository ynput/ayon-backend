from typing import Literal

from fastapi import Query

from ayon_server.api.dependencies import ProjectName
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router

ReviewableType = Literal["image", "video"]


class ReviewableModel(OPModel):
    file_id: str = Field(..., title="Reviewable ID")
    activity_id: str = Field(..., title="Activity ID")
    filename: str = Field(..., title="Reviewable Name")
    label: str | None = Field(None, title="Reviewable Label")
    mimetype: str = Field(..., title="Reviewable Mimetype")
    version_id: str = Field(..., title="Version ID")
    version: int = Field(..., title="Version")
    previewable: bool = Field(True, title="Is the file previewable?")


class ReviewableListModel(OPModel):
    reviewables: list[ReviewableModel]


@router.get("")
async def list_reviewables(
    # user: CurrentUser,
    project_name: ProjectName,
    product_id: str = Query(..., description="Product ID", alias="product"),
) -> ReviewableListModel:
    """Returns a list of reviewables for a given product."""

    query = f"""
        SELECT
            files.id as file_id,
            af.activity_id as activity_id,
            files.data->>'mime' AS mimetype,
            files.data->>'filename' AS filename,
            files.data->>'label' AS label,

            versions.id AS version_id,
            versions.version AS version

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
            versions.product_id = $1

    """

    reviewables: list[ReviewableModel] = []
    async for row in Postgres.iterate(query, product_id):
        reviewables.append(ReviewableModel(**row))

    return ReviewableListModel(reviewables=reviewables)

from fastapi import Depends

from ayon_server.api.dependencies import dep_current_user, dep_project_name
from ayon_server.entities import UserEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router


class EntityCounts(OPModel):
    folders: int = Field(..., description="Number of folders", example=10)
    subsets: int = Field(..., description="Number of subsets", example=98)
    versions: int = Field(..., description="Number of versions", example=512)
    representations: int = Field(
        ...,
        description="Number of representations",
        example=4853,
    )
    tasks: int = Field(..., description="Number of tasks", example=240)
    workfiles: int = Field(..., description="Number of workfiles", example=190)


@router.get("/entities", response_model=EntityCounts)
async def get_project_entity_counts(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Retrieve entity counts for a given project."""

    counts = {}
    for entity in [
        "folders",
        "subsets",
        "versions",
        "representations",
        "tasks",
        "workfiles",
    ]:
        res = await Postgres.fetch(
            f"""
            SELECT COUNT(id)
            FROM project_{project_name}.{entity}
            """
        )
        counts[entity] = res[0][0]

    return EntityCounts(**counts)

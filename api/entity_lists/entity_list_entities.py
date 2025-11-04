from typing import Annotated

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel, ProjectLevelEntityType

from .router import router


class EntityListEnities(OPModel):
    entity_type: Annotated[ProjectLevelEntityType, Field(title="Entity type")]
    entity_ids: Annotated[list[str], Field(title="Entity IDs")]


@router.get("/lists/{list_id}/entities")
async def get_list_entities(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
) -> EntityListEnities:
    """Get the entities of a list."""

    query = f"""
        SELECT
            DISTINCT (i.entity_id),
            l.entity_type entity_type
        FROM project_{project_name}.entity_lists l
        JOIN
            project_{project_name}.entity_list_items i
            ON l.id = i.entity_list_id
        WHERE l.id = $1
    """

    entity_type: ProjectLevelEntityType | None = None
    entity_ids: set[str] = set()

    async for row in Postgres.iterate(query, list_id):
        entity_type = row["entity_type"]
        entity_ids.add(row["entity_id"])

    if entity_type is None:
        raise NotFoundException(
            f"Entity list ID '{list_id}' not found",
        )

    return EntityListEnities(
        entity_type=entity_type,
        entity_ids=list(entity_ids),
    )

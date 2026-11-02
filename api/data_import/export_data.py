from fastapi import HTTPException

from ayon_server.api.dependencies import CurrentUser
from ayon_server.entity_lists import EntityList
from ayon_server.helpers.project_list import normalize_project_name
from ayon_server.types import ProjectLevelEntityType

from .common import ImportEntityType, ProjectNameQuery
from .models import EXPORTABLE_ENTITIES, ImportableColumn
from .router import router


@router.get("/export/{entity_type}/fields")
async def export_fields(
    entity_type: ImportEntityType,
    user: CurrentUser,
    project_name: ProjectNameQuery = None,
    folder_id: str | None = None,
    list_entity_type: ProjectLevelEntityType | None = None,
) -> list[ImportableColumn] | None:
    """Get exportable fields for an entity type.

    Args:
        entity_type: The type of entity (user, folder, task, hierarchy)
        project_name: Project name for resolving project-specific enums.
        folder_id: The entity list for list items, adds its attribute columns
        list_entity_type: For list items without a list, the entity type of a
            new list, adds the columns of its entities
    """

    # Validate entity type exists
    if entity_type not in EXPORTABLE_ENTITIES:
        raise HTTPException(
            status_code=404, detail=f"Entity type '{entity_type}' not implemented"
        )

    if project_name is not None:
        project_name = await normalize_project_name(project_name)

    if entity_type == "entity_list_item" and project_name and folder_id:
        entity_list = await EntityList.load(project_name, folder_id, user=user)
        await entity_list.ensure_can_read()
    else:
        folder_id = None

    model = EXPORTABLE_ENTITIES[entity_type]
    return await model.fields(
        project_name=project_name,
        parent_id=folder_id,
        list_entity_type=list_entity_type
        if entity_type == "entity_list_item"
        else None,
    )

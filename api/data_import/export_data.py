from fastapi import HTTPException

from ayon_server.helpers.project_list import normalize_project_name

from .common import ImportEntityType, ProjectNameQuery
from .models import EXPORTABLE_ENTITIES, ImportableColumn
from .router import router


@router.get("/export/{entity_type}/fields")
async def export_fields(
    entity_type: ImportEntityType,
    project_name: ProjectNameQuery = None,
) -> list[ImportableColumn] | None:
    """Get exportable fields for an entity type.

    Args:
        entity_type: The type of entity (user, folder, task, hierarchy)
        project_name: Project name for resolving project-specific enums.
    """

    # Validate entity type exists
    if entity_type not in EXPORTABLE_ENTITIES:
        raise HTTPException(
            status_code=404, detail=f"Entity type '{entity_type}' not implemented"
        )

    if project_name is not None:
        project_name = await normalize_project_name(project_name)

    model = EXPORTABLE_ENTITIES[entity_type]
    return await model.fields(project_name=project_name)

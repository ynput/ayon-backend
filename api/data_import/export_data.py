import csv
import os
import tempfile

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, Response


from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.project_list import normalize_project_name

from .common import ProjectNameQuery, ImportEntityType
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


@router.post("/export/{entity_type}")
async def export(
    entity_type: ImportEntityType,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    project_name: ProjectNameQuery = None,
    field_names: list[str] | None = None,
    entity_ids: tuple[str, list[str]] | None = None,
) -> Response:
    """Export entity data as CSV."""
    if not user.is_manager:
        raise ForbiddenException("You must be a manager")

    if project_name is not None:
        project_name = await normalize_project_name(project_name)

    # Validate entity type exists
    if entity_type not in EXPORTABLE_ENTITIES:
        raise HTTPException(
            status_code=404, detail=f"Entity type '{entity_type}' not implemented"
        )

    storage_dir = tempfile.mkdtemp(prefix="ayon_export_")

    if entity_type == "user":
        user.check_permissions("studio.list_all_users")
    elif entity_type in ["folder", "task"]:
        user.check_permissions("project.access", project_name)

    model_cls = EXPORTABLE_ENTITIES[entity_type]
    rows = await model_cls().get_all_items(
        field_names, True, project_name=project_name, entity_ids=entity_ids
    )

    export_path = os.path.join(storage_dir, f"{entity_type}_export.csv")
    with open(export_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    if background_tasks:
        background_tasks.add_task(_cleanup_file, export_path, storage_dir)

    return FileResponse(
        export_path, media_type="text/csv", filename=f"{entity_type}_export.csv"
    )


def _cleanup_file(file_path: str, temp_dir: str) -> None:
    """Delete a file and its parent temp directory after the response is sent."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
    except Exception:
        pass  # Silent fail for cleanup

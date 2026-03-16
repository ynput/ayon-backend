import csv
import os
from typing import Any, Optional, Tuple

from fastapi import HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, Response

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException
from ayon_server.files import Storages

from .models import EXPORTABLE_ENTITIES

from .router import router


@router.get("/export/{entity_type}/fields")
async def export_fields(
    entity_type: str,
) -> Optional[list[dict[str, Any]]]:
    """Get exportable fields for an entity type."""

    # Validate entity type exists
    if entity_type not in EXPORTABLE_ENTITIES:
        raise HTTPException(
            status_code=404,
            detail=f"Entity type '{entity_type}' not implemented"
        )

    model = EXPORTABLE_ENTITIES[entity_type]
    return model.fields()


@router.post("/export/{entity_type}")
async def export(
    entity_type: str,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    project_name: Optional[str] = None,
    field_names: Optional[list[str]] = None,
    entity_ids: Optional[Tuple[str, list[str]]] = None,
) -> Response:
    """Export entity data as CSV."""
    if not user.is_manager:
        raise ForbiddenException("You must be a manager")

    # Validate entity type exists
    if entity_type not in EXPORTABLE_ENTITIES:
        raise HTTPException(
            status_code=404,
            detail=f"Entity type '{entity_type}' not implemented"
        )

    project_storage = await Storages.project(project_name)
    storage_dir = await project_storage.get_root()
    storage_dir = os.path.join(storage_dir, "data_import/exports")
    os.makedirs(storage_dir, exist_ok=True)

    if entity_type == "user":
        user.check_permissions("studio.list_all_users")
    elif entity_type in ["folder", "task"]:
        user.check_permissions("project.access", project_name)

    model_cls = EXPORTABLE_ENTITIES[entity_type]
    rows = await model_cls().get_all_items(
        field_names,
        True,
        project_name=project_name,
        entity_ids=entity_ids
    )

    export_path = os.path.join(storage_dir, f"{entity_type}_export.csv")
    with open(export_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    if background_tasks:
        background_tasks.add_task(_cleanup_file, export_path)

    return FileResponse(
        export_path,
        media_type="text/csv",
        filename=f"{entity_type}_export.csv"
    )


def _cleanup_file(file_path: str) -> None:
    """Delete a file after the response is sent."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        pass  # Silent fail for cleanup

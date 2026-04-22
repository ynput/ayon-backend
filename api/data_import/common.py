from typing import Annotated
from fastapi import Query

from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import PROJECT_NAME_REGEX

# Sender type for operations status propagation
SENDER_TYPE = "data_import"


ProjectNameQuery = Annotated[
    str | None,
    Query(alias="project_name", regex=PROJECT_NAME_REGEX)
]


async def get_entity_id_by_path(
    project_name: str | None, path: str | None, is_task: bool = False
) -> str:
    """Get folder or task id by its path.

    Args:
        project_name: Project name
        path: Entity path (folder path or "folder_path/task_name" for tasks)
        is_task: Whether to look for a task

    Returns:
        Entity ID

    Raises:
        NotFoundException: If entity not found
    """
    if project_name is None:
        raise NotFoundException("Cannot find entity without project name")
    if path is None:
        raise NotFoundException("Entity with path 'None' not found in the database")
    folder_path = path.replace("\\", "/").replace(" ", "")
    task_name = None

    if is_task:
        folder_path, task_name = folder_path.rsplit("/", 1)

    folder_path = folder_path.lstrip("/")
    # Query for folder
    query = f"""
        SELECT h.id, h.path
        FROM project_{project_name}.hierarchy h
        WHERE h.path = $1
    """
    result = await Postgres.fetchrow(query, folder_path)

    if not result:
        raise NotFoundException(
            f"Entity with path '{folder_path}' not found in the database"
        )

    # For tasks, also query for the task
    if is_task:
        query = f"""
            SELECT id
            FROM project_{project_name}.tasks
            WHERE folder_id = $1 AND name = $2
        """
        result = await Postgres.fetchrow(query, result["id"], task_name)
        if not result:
            raise NotFoundException(
                f"Entity with path '{folder_path}' not found in the database"
            )

    return result["id"]

from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres

# Sender type for operations status propagation
SENDER_TYPE = "data_import"

async def _get_entity_id_by_path(
    project_name: str,
    path: str,
    is_task: bool = False
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
        result = await Postgres.fetchrow(
            query,
            result["id"],
            task_name
        )
        if not result:
            raise NotFoundException(
                f"Entity with path '{folder_path}' not found in the database"
            )

    return result["id"]


async def _get_entity_ids_by_name(
    project_name: str,
    entity_name: str,
    entity_type: str,
) -> list[str]:
    """Get folder or task id by its name.

    Args:
        project_name: Project name
        entity_name: Entity name
        entity_type: Entity type

    Returns:
        list[str]: Entity IDs
    """
    if entity_type.lower() not in ["folder", "task"]:
        raise ValueError(f"Invalid entity type '{entity_type}'")

    query = f"""
        SELECT id
        FROM project_{project_name}.{entity_type.lower()}s
        WHERE name = $1
    """
    entity_ids = []
    async for row in Postgres.iterate(query, entity_name):
        entity_ids.append(row["id"])

    return entity_ids

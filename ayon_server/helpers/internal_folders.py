from ayon_server.entities.folder import FolderEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.operations.project_level import ProjectLevelOperations
from ayon_server.utils import create_uuid


async def get_default_folder_type(project_name: str) -> str:
    """Get default folder type for project"""
    query = f"""
        SELECT name FROM project_{project_name}.folder_types
        ORDER BY position ASC LIMIT 1
    """
    res = await Postgres.fetchrow(query)
    if not res:
        # this should not happen
        raise RuntimeError(
            f"Project {project_name} does not have any folder types defined"
        )
    return res["name"]


async def get_internal_folder(project_name: str, key: str) -> FolderEntity:
    """Get internal folder id by key"""

    expected_root_path = "__ayon_internal__"
    expected_path = f"__ayon_internal__/{key}"

    query = f"""
        SELECT id, path FROM project_{project_name}.hierarchy
        WHERE path IN ($1, $2)
    """

    root_folder_id = None
    folder_id = None

    res = await Postgres.fetch(query, expected_root_path, expected_path)
    for row in res:
        if row["path"] == expected_root_path:
            root_folder_id = row["id"]
        elif row["path"] == expected_path:
            folder_id = row["id"]

    default_folder_type = await get_default_folder_type(project_name)

    ops = ProjectLevelOperations(project_name)

    if not root_folder_id:
        root_folder_id = create_uuid()
        ops.create(
            "folder",
            entity_id=root_folder_id,
            parent_id=None,
            name="__ayon_internal__",
            folder_type=default_folder_type,
        )

    if not folder_id:
        folder_id = create_uuid()
        ops.create(
            "folder",
            name=key,
            entity_id=folder_id,
            parent_id=root_folder_id,
            folder_type=default_folder_type,
        )

    await ops.process()

    return await FolderEntity.load(project_name, folder_id)

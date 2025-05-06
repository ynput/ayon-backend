from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Connection, Postgres
from ayon_server.types import ProjectLevelEntityType


async def _get_entity_folder_path(
    project_name: str,
    entity_type: ProjectLevelEntityType,
    entity_id: str,
    conn: Connection,
) -> str:
    """Get the parent folder path of an entity

    We store the path in the list item record in order to solve
    access control.
    """
    joins = []
    await conn.execute(f"SET LOCAL search_path TO project_{project_name}")

    if entity_type in ("product", "version", "representation"):
        joins.append(
            """
            INNER JOIN products
            ON products.folder_id = folders.id
            """
        )
        if entity_type in ("version", "representation"):
            joins.append(
                """
                INNER JOIN versions
                ON versions.product_id = products.id
                """
            )
            if entity_type == "representation":
                joins.append(
                    """
                    INNER JOIN representations
                    ON representations.version_id = versions.id
                    """
                )

    elif entity_type in ("task", "workfile"):
        joins.append(
            """
            INNER JOIN tasks
            ON tasks.folder_id = folders.id
            """
        )

        if entity_type == "workfile":
            joins.append(
                """
                INNER JOIN workfiles
                ON workfiles.task_id = tasks.id
                """
            )

    query = f"""
    SELECT folders.path as path
    FROM hierarchy as folders
    {' '.join(joins)}
    WHERE {entity_type}s.id = $1
    """
    res = await conn.fetchrow(query, entity_id)
    if not res:
        raise NotFoundException(f"{entity_type.capitalize()} {entity_id} not found")
    return res["path"]


async def get_entity_folder_path(
    project_name: str,
    entity_type: ProjectLevelEntityType,
    entity_id: str,
    *,
    conn: Connection | None = None,
) -> str:
    if conn is None:
        async with Postgres.acquire() as conn, conn.transaction():
            return await _get_entity_folder_path(
                project_name,
                entity_type,
                entity_id,
                conn,
            )

    return await _get_entity_folder_path(
        project_name,
        entity_type,
        entity_id,
        conn,
    )

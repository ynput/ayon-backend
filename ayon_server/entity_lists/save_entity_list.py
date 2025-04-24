from ayon_server.lib.postgres import Connection, Postgres

from .models import EntityListModel


async def _save_entity_list(
    project_name: str,
    payload: EntityListModel,
    conn: Connection,
) -> None:
    """
    Save the entity list to the database.

    If the list with the same ID already exists, it will be updated.
    """

    await conn.execute(f"SET LOCAL search_path TO project_{project_name}")

    query = """
    INSERT INTO entity_lists (
        id,
        entity_list_type,
        entity_type,
        label,
        owner,
        access,
        template,
        attrib,
        data,
        tags,
        active,
        created_at,
        created_by,
        updated_by
    ) VALUES (
      $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
    ) ON CONFLICT (id) DO UPDATE SET
        entity_list_type = $2,
        entity_type = $3,
        label = $4,
        owner = $5,
        access = $6,
        template = $7,
        attrib = $8,
        data = $9,
        tags = $10,
        active = $11,
        updated_at = NOW(),
        updated_by = $14
    """

    await conn.execute(
        query,
        payload.id,  # 1
        payload.entity_list_type,  # 2
        payload.entity_type,  # 3
        payload.label,  # 4
        payload.owner,  # 5
        payload.access,  # 6
        payload.template,  # 7
        payload.attrib,  # 8
        payload.data,  # 9
        payload.tags,  # 10
        payload.active,  # 11
        payload.created_at,  # 12
        payload.created_by,  # 13
        payload.updated_by,  # 14
    )


async def save_entity_list(
    project_name: str,
    payload: EntityListModel,
    conn: Connection | None = None,
) -> None:
    """
    Save the entity list to the database.
    If the list with the same ID already exists, it will be updated.
    """

    if conn is None:
        async with Postgres.acquire() as conn, conn.transaction():
            await _save_entity_list(project_name, payload, conn)
    else:
        await _save_entity_list(project_name, payload, conn)

from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Connection, Postgres

from .models import EntityListItemModel, EntityListModel


async def _load_entity_list(
    project_name: str,
    entity_list_id: str,
    conn: Connection,
) -> EntityListModel:
    await conn.execute(f"SET LOCAL search_path TO project_{project_name}")
    query = "SELECT * FROM entity_lists WHERE id = $1"
    res = await conn.fetchrow(query, entity_list_id)
    if not res:
        raise NotFoundException(f"Entity list {entity_list_id} not found")

    item_query = """
        SELECT * FROM entity_list_items
        WHERE entity_list_id = $1 ORDER BY position
    """

    items = []
    stmt = await conn.prepare(item_query)
    async for row in stmt.cursor(res["id"]):
        item = EntityListItemModel(**row)
        items.append(item)

    return EntityListModel(**res, items=items)


async def load_entity_list(
    project_name: str,
    entity_list_id: str,
    conn: Connection | None = None,
) -> EntityListModel:
    """Load an entity list and its items from the database."""

    if conn is None:
        async with Postgres.acquire() as conn, conn.transaction():
            return await _load_entity_list(project_name, entity_list_id, conn)

    return await _load_entity_list(project_name, entity_list_id, conn)

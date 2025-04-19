from ayon_server.entities import UserEntity
from ayon_server.entity_lists.summary import EntityListSummary, get_entity_list_summary
from ayon_server.events import EventStream
from ayon_server.lib.postgres import Connection, Postgres


async def delete_entity_list(
    project_name: str,
    list_id: str,
    *,
    user: UserEntity | None = None,
    conn: Connection | None = None,
) -> None:
    """Delete entity list"""

    async def execute_delete(conn: Connection) -> EntityListSummary:
        summary = await get_entity_list_summary(conn, project_name, list_id)
        query = "DELETE FROM entity_lists WHERE id = $1"
        await conn.execute(f"SET LOCAL search_path TO project_{project_name}")
        await conn.execute(query, list_id)
        return summary

    if conn is None:
        async with Postgres.acquire() as conn, conn.transaction():
            summary = await execute_delete(conn)
    else:
        summary = await execute_delete(conn)

    await EventStream.dispatch(
        "entity_list_deleted",
        summary=summary.dict(),
        description=f"Deleted entity list {summary.label}",
        project=project_name,
        user=user.name if user else None,
    )

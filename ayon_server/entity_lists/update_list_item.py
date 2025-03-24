from typing import Any

from ayon_server.entities import UserEntity
from ayon_server.lib.postgres import Connection, Postgres


async def _change_list_item_postion(
    conn: Connection,
    project_name: str,
    list_item_id: str,
    new_position: int,
) -> None:
    await conn.execute(f"SET LOCAL search_path TO project_{project_name}")

    query = """
    -- Get the old position of the item we're moving

    WITH item_info AS (
        SELECT entity_list_id, position as old_position
        FROM entity_list_items WHERE id = $1
    )

    UPDATE entity_list_items
    SET position =
        CASE
            WHEN id = $1 THEN $2

            WHEN position > (SELECT old_position FROM item_info)
                AND position <= $2 THEN
                position - 1

            WHEN position >= $2
                AND position < (SELECT old_position FROM item) THEN
                position + 1

            ELSE position
        END
    WHERE
        entity_list_id = (SELECT entity_list_id FROM item)
        position
            BETWEEN LEAST($2, (SELECT old_position FROM item))
            AND GREATEST($2, (SELECT old_position FROM item))
    OR
        id = $1;
    """

    await conn.execute(query, list_item_id, new_position)


async def change_list_item_position(
    project_name: str,
    list_item_id: str,
    new_position: int,
    conn: Connection | None = None,
) -> None:
    pass

    if conn is None:
        async with Postgres.acquire() as conn, conn.transaction():
            return await _change_list_item_postion(
                conn,
                project_name,
                list_item_id,
                new_position,
            )

    await _change_list_item_postion(
        conn,
        project_name,
        list_item_id,
        new_position,
    )


async def _update_list_item(
    conn: Connection,
    project_name: str,
    list_item_id: str,
    *,
    label: str | None = None,
    position: int | None = None,
    owner: str | None = None,
    access: dict[str, Any] | None = None,
    attributes: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    active: bool | None = None,
    user: UserEntity | None = None,
):
    pass


async def update_list_item(
    project_name: str,
    list_item_id: str,
    *,
    label: str | None = None,
    position: int | None = None,
    owner: str | None = None,
    access: dict[str, Any] | None = None,
    attributes: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    active: bool | None = None,
    user: UserEntity | None = None,
    conn: Connection | None = None,
):
    if conn is not None:
        return await _update_list_item(
            conn,
            project_name,
            list_item_id,
            label=label,
            position=position,
            owner=owner,
            access=access,
            attributes=attributes,
            data=data,
            tags=tags,
            active=active,
            user=user,
        )

    async with Postgres.acquire() as conn, conn.transaction():
        return await _update_list_item(
            conn,
            project_name,
            list_item_id,
            label=label,
            position=position,
            owner=owner,
            access=access,
            attributes=attributes,
            data=data,
            tags=tags,
            active=active,
            user=user,
        )

from datetime import datetime
from typing import Any

from ayon_server.entities import UserEntity
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Connection, Postgres

from .summary import on_list_items_changed


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
                AND position < (SELECT old_position FROM item_info) THEN
                position + 1

            ELSE position
        END
    WHERE
        entity_list_id = (SELECT entity_list_id FROM item_info)
    AND position
        BETWEEN LEAST($2, (SELECT old_position FROM item_info))
        AND GREATEST($2, (SELECT old_position FROM item_info))
    OR
        id = $1;
    """

    await conn.execute(query, list_item_id, new_position)


# TODO: Do we need this???
async def change_list_item_position(
    project_name: str,
    list_item_id: str,
    new_position: int,
    conn: Connection | None = None,
) -> None:
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


def merge_jsonb_fields(
    old_data: dict[str, Any],
    new_data: dict[str, Any],
) -> dict[str, Any]:
    merged_data = old_data.copy()
    for key, value in new_data.items():
        if value is None:
            merged_data.pop(key, None)
        else:
            merged_data[key] = value
    return merged_data


UPDATEABLE_FIELDS = [
    "label",
    "position",
    "attrib",
    "data",
    "tags",
]


async def _update_list_item(
    conn: Connection,
    project_name: str,
    entity_list_id: str,
    list_item_id: str,
    *,
    label: str | None = None,
    position: int | None = None,
    attrib: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    user: UserEntity | None = None,
    sender: str | None = None,
    sender_type: str | None = None,
    run_post_update_hook: bool = True,
):
    await conn.execute(f"SET LOCAL search_path TO project_{project_name}")

    select_query = f"""
        SELECT {','.join(UPDATEABLE_FIELDS)}
        FROM entity_list_items WHERE id = $1
    """
    result = await conn.fetchrow(select_query, list_item_id)
    if result is None:
        raise NotFoundException(f"Entity list item with ID '{list_item_id}' not found")

    update_dict = dict(result)
    update_dict["updated_at"] = datetime.utcnow()

    if user is not None:
        update_dict["updated_by"] = user.name

    if label is not None:
        update_dict["label"] = label

    if tags is not None:
        update_dict["tags"] = tags

    # JSONB fields

    if attrib is not None:
        update_dict["attrib"] = merge_jsonb_fields(update_dict["attrib"], attrib)

    if data is not None:
        update_dict["data"] = merge_jsonb_fields(update_dict["data"], data)

    # Construct the update query

    update_statements: list[str] = []
    update_values: list[Any] = []

    for key, value in update_dict.items():
        index = len(update_statements) + 1
        update_statements.append(f"{key} = ${index}")
        update_values.append(value)

    id_idx = len(update_statements) + 1
    update_values.append(list_item_id)
    query = f"""
        UPDATE entity_list_items SET
        {', '.join(update_statements)}
        WHERE id = ${id_idx}
    """

    if update_statements:
        await conn.execute(query, *update_values)

    # When position has changed, run the helper function

    if position is not None:
        await _change_list_item_postion(
            conn,
            project_name,
            list_item_id,
            position,
        )

    if run_post_update_hook and (update_statements or position is not None):
        await on_list_items_changed(conn, project_name, entity_list_id, user=user)


async def update_list_item(
    project_name: str,
    entity_list_id: str,
    list_item_id: str,
    *,
    label: str | None = None,
    position: int | None = None,
    attrib: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    user: UserEntity | None = None,
    sender: str | None = None,
    sender_type: str | None = None,
    conn: Connection | None = None,
    run_post_update_hook: bool = True,
):
    if conn is not None:
        return await _update_list_item(
            conn,
            project_name,
            entity_list_id,
            list_item_id,
            label=label,
            position=position,
            attrib=attrib,
            data=data,
            tags=tags,
            user=user,
            sender=sender,
            sender_type=sender_type,
        )

    async with Postgres.acquire() as conn, conn.transaction():
        return await _update_list_item(
            conn,
            project_name,
            entity_list_id,
            list_item_id,
            label=label,
            position=position,
            attrib=attrib,
            data=data,
            tags=tags,
            user=user,
            sender=sender,
            sender_type=sender_type,
        )

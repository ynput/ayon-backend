from datetime import datetime
from typing import Any

from ayon_server.entities import UserEntity
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


async def _update_list_item(
    conn: Connection,
    project_name: str,
    entity_list_id: str,
    list_item_id: str,
    *,
    label: str | None = None,
    position: int | None = None,
    owner: str | None = None,
    access: dict[str, Any] | None = None,
    attrib: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    active: bool | None = None,
    user: UserEntity | None = None,
    sender: str | None = None,
    sender_type: str | None = None,
    run_post_update_hook: bool = True,
):
    update_dict: dict[str, Any] = {"updated_at": datetime.utcnow()}
    if user is not None:
        update_dict["updated_by"] = user.name

    if label is not None:
        update_dict["label"] = label

    if owner is not None:
        # TODO: manager only
        update_dict["owner"] = owner

    if access is not None:
        # TODO: manager only
        update_dict["access"] = access

    if attrib is not None:
        update_dict["attrib"] = attrib

    if data is not None:
        update_dict["data"] = data

    if tags is not None:
        update_dict["tags"] = tags

    if active is not None:
        update_dict["active"] = active

    # Construct the update query

    update_statements = []
    update_values = []
    jsonb_fields = ["access", "attrib", "data"]

    for key, value in update_dict.items():
        if key in jsonb_fields and isinstance(value, dict):
            for sub_key, sub_value in value.items():
                index = len(update_statements) + 1
                if sub_value is None:
                    # Remove the key from the JSONB field
                    update_statements.append(f"{key} = {key} - '${index}'")
                    update_values.append(sub_key)
                else:
                    # Update or add the key in the JSONB field
                    update_statements.append(
                        f"{key} = jsonb_set({key}, '{{{sub_key}}}', ${index}::jsonb, true)"  # noqa: E501
                    )
                    update_values.append(sub_value)

        else:
            index = len(update_statements) + 1
            update_statements.append(f"{key} = ${index}")

    id_idx = len(update_statements) + 1
    update_values.append(list_item_id)
    query = f"""
        UPDATE entity_lists SET
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
    owner: str | None = None,
    access: dict[str, Any] | None = None,
    attrib: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    active: bool | None = None,
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
            owner=owner,
            access=access,
            attrib=attrib,
            data=data,
            tags=tags,
            active=active,
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
            owner=owner,
            access=access,
            attrib=attrib,
            data=data,
            tags=tags,
            active=active,
            user=user,
            sender=sender,
            sender_type=sender_type,
        )

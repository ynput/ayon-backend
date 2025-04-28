from ayon_server.entities import UserEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import AyonException
from ayon_server.lib.postgres import Connection, Postgres

from .models import EntityListModel, EntityListSummary


async def _save_entity_list(
    project_name: str,
    payload: EntityListModel,
    *,
    user: UserEntity | None = None,
    sender: str | None = None,
    sender_type: str | None = None,
    conn: Connection,
) -> EntityListSummary:
    """
    Save the entity list to the database.

    If the list with the same ID already exists, it will be updated.
    """

    await conn.execute(f"SET LOCAL search_path TO project_{project_name}")

    payload.data["count"] = len(payload.items)

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
    RETURNING xmax = 0 AS inserted;
    """

    # Map SQL query placeholders to corresponding payload attributes

    res = await conn.fetchrow(
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
    if not res:
        raise AyonException("Failed to save entity list")

    mode = "created" if res["inserted"] else "changed"

    item_ids = {item.id for item in payload.items}
    if item_ids:
        await conn.execute(
            """
            DELETE FROM entity_list_items
            WHERE entity_list_id = $1
            AND NOT (id = ANY($2))
            """,
            payload.id,
            item_ids,
        )

        for item in payload.items:
            await conn.execute(
                """
                INSERT INTO entity_list_items (
                    id,
                    entity_list_id,
                    entity_id,
                    position,
                    label,
                    attrib,
                    data,
                    tags,
                    folder_path,
                    created_at,
                    created_by,
                    updated_at,
                    updated_by
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), $10, NOW(), $11)
                ON CONFLICT (id) DO UPDATE SET
                    entity_list_id = $2,
                    entity_id = $3,
                    position = $4,
                    label = $5,
                    attrib = $6,
                    data = $7,
                    tags = $8,
                    folder_path = $9,
                    updated_at = NOW(),
                    updated_by = $11
                """,
                item.id,
                payload.id,
                item.entity_id,
                item.position,
                item.label,
                item.attrib,
                item.data,
                item.tags,
                item.folder_path,
                payload.created_by,
                payload.updated_by,
            )
    else:
        await conn.execute(
            """
            DELETE FROM entity_list_items
            WHERE entity_list_id = $1
            """,
            payload.id,
        )

    summary = EntityListSummary(
        id=payload.id,
        entity_list_type=payload.entity_list_type,
        entity_type=payload.entity_type,
        label=payload.label,
        count=len(payload.items),
    )

    description = f"Entity list {payload.label} {mode}"

    await EventStream.dispatch(
        f"entity_list.{mode}",
        description=description,
        summary=summary.dict(),
        project=project_name,
        user=user.name if user else None,
        sender=sender,
        sender_type=sender_type,
    )
    return summary


#
# Transaction wrapper
#


async def save_entity_list(
    project_name: str,
    payload: EntityListModel,
    *,
    user: UserEntity | None = None,
    sender: str | None = None,
    sender_type: str | None = None,
    conn: Connection | None = None,
) -> EntityListSummary:
    """
    Save the entity list to the database.
    If the list with the same ID already exists, it will be updated.
    """

    if conn is None:
        async with Postgres.acquire() as conn, conn.transaction():
            return await _save_entity_list(
                project_name,
                payload,
                user=user,
                sender=sender,
                sender_type=sender_type,
                conn=conn,
            )
    else:
        return await _save_entity_list(
            project_name,
            payload,
            user=user,
            sender=sender,
            sender_type=sender_type,
            conn=conn,
        )

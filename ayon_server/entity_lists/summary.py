from typing import NotRequired, Required, TypedDict

from ayon_server.entities import UserEntity
from ayon_server.events import EventStream
from ayon_server.lib.postgres import Connection

ENTITY_LIST_SUMMARY_EVENT_FIELDS = ["id", "list_type", "label"]


class EntityListSummary(TypedDict):
    # this only goes to the event stream

    id: Required[str]
    list_type: Required[str]
    label: Required[str]

    # the following goes to data (and event stream)

    folder_count: NotRequired[int]
    task_count: NotRequired[int]
    product_count: NotRequired[int]
    version_count: NotRequired[int]
    representation_count: NotRequired[int]
    workfile_count: NotRequired[int]


async def get_entity_list_summary(
    conn: Connection, project_name: str, entity_list_id: str
) -> EntityListSummary:
    """
    Entity list summary is stored in entity_list.data
    as well as in the event created by creating or updating entity list.
    """

    res = await conn.fetch(
        f"""
        SELECT list_type, label FROM project_{project_name}.entity_lists
        WHERE id = $1
    """,
        entity_list_id,
    )
    result: EntityListSummary = {
        "id": entity_list_id,
        "list_type": res[0]["list_type"],
        "label": res[0]["label"],
    }
    query = f"""
        SELECT entity_type, count(*) as count
        FROM project_{project_name}.entity_list_items
        WHERE entity_list_id = $1
        GROUP BY entity_type;
    """
    res = await conn.fetch(query, entity_list_id)
    for row in res:
        result[f"{row['entity_type']}_count"] = row["count"]  # type: ignore

    return result


async def on_list_items_changed(
    conn: Connection,
    project_name: str,
    entity_list_id: str,
    *,
    description: str = "Entity list {label} items changed",
    user: UserEntity | None = None,
    sender: str | None = None,
    sender_type: str | None = None,
) -> EntityListSummary:
    summary = await get_entity_list_summary(conn, project_name, entity_list_id)
    payload = {
        k: v for k, v in summary.items() if k not in ENTITY_LIST_SUMMARY_EVENT_FIELDS
    }
    await conn.execute(
        f"""
        UPDATE project_{project_name}.entity_lists
        SET data = jsonb_set(data, '{{summary}}', $1::jsonb)
        WHERE id = $2
    """,
        payload,
        entity_list_id,
    )

    description = description.format(label=summary["label"])

    await EventStream.dispatch(
        "entity_list.items_changed",
        description=description,
        summary=dict(summary),
        project=project_name,
        user=user.name if user else None,
        sender=sender,
        sender_type=sender_type,
    )
    return summary

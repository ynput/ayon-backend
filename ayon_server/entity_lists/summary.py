from typing import NotRequired, Required, TypedDict

from ayon_server.lib.postgres import Connection

ENTITY_LIST_SUMMARY_EVENT_FIELDS = ["id", "entity_list_type", "label"]


class EntityListSummary(TypedDict):
    # this only goes to the event stream

    id: Required[str]
    entity_list_type: Required[str]
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
        SELECT entity_list_type, label FROM project_{project_name}.entity_lists
        WHERE id = $1
    """,
        entity_list_id,
    )
    result: EntityListSummary = {
        "id": entity_list_id,
        "entity_list_type": res[0]["entity_list_type"],
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

from typing import Annotated, Any

from ayon_server.entities import UserEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Connection
from ayon_server.types import Field, OPModel, ProjectLevelEntityType
from ayon_server.utils import create_uuid


class EntityListSummary(OPModel):
    id: Annotated[str, Field(..., title="List ID", example=create_uuid())]
    entity_list_type: Annotated[
        str | None,
        Field(
            title="Entity list type",
            description="Type of the entity list",
            example="generic",
        ),
    ]
    entity_type: Annotated[
        ProjectLevelEntityType,
        Field(
            title="Entity Type",
            description="Entity type that can be included in the list",
            example="task",
        ),
    ]
    label: Annotated[str, Field(..., title="Label", example="My List")]
    count: Annotated[int, Field(title="Item count", ge=0)] = 0

    def get_summary_data(self) -> dict[str, Any]:
        return {"count": self.count}


async def get_entity_list_summary(
    conn: Connection,
    project_name: str,
    entity_list_id: str,
) -> EntityListSummary:
    """
    Entity list summary is stored in entity_list.data
    as well as in the event created by creating or updating entity list.
    """

    res = await conn.fetchrow(
        f"""
        SELECT entity_list_type, entity_type, label
        FROM project_{project_name}.entity_lists
        WHERE id = $1
    """,
        entity_list_id,
    )
    if res is None:
        raise NotFoundException(f"Entity list with id {entity_list_id} not found")

    result = EntityListSummary(
        id=entity_list_id,
        entity_list_type=res["entity_list_type"],
        entity_type=res["entity_type"],
        label=res["label"],
    )
    query = f"""
        SELECT count(*) as count
        FROM project_{project_name}.entity_list_items
        WHERE entity_list_id = $1
    """
    res = await conn.fetchrow(query, entity_list_id)
    assert res is not None, f"Entity list with id {entity_list_id} not found"
    setattr(result, "count", res["count"])
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
    await conn.execute(
        f"""
        UPDATE project_{project_name}.entity_lists
        SET data = jsonb_set(data, '{{summary}}', $1::jsonb)
        WHERE id = $2
    """,
        summary.get_summary_data(),
        entity_list_id,
    )

    description = description.format(label=summary.label)

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

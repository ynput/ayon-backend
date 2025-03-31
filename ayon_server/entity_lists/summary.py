from typing import Annotated, Any

from ayon_server.entities import UserEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Connection
from ayon_server.types import Field, OPModel
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
    label: Annotated[str, Field(..., title="Label", example="My List")]

    folders: Annotated[int, Field(title="Folder count", ge=0)] = 0
    tasks: Annotated[int, Field(title="Task count", ge=0)] = 0
    products: Annotated[int, Field(title="Product count", ge=0)] = 0
    versions: Annotated[int, Field(title="Version count", ge=0)] = 0
    representations: Annotated[int, Field(title="Representation count", ge=0)] = 0
    workfiles: Annotated[int, Field(title="Workfile count", ge=0)] = 0

    def get_summary_data(self) -> dict[str, Any]:
        data = {
            "folders": self.folders,
            "tasks": self.tasks,
            "products": self.products,
            "versions": self.versions,
            "representations": self.representations,
            "workfiles": self.workfiles,
        }
        return {k: v for k, v in data.items() if v > 0}


async def get_entity_list_summary(
    conn: Connection, project_name: str, entity_list_id: str
) -> EntityListSummary:
    """
    Entity list summary is stored in entity_list.data
    as well as in the event created by creating or updating entity list.
    """

    res = await conn.fetchrow(
        f"""
        SELECT entity_list_type, label FROM project_{project_name}.entity_lists
        WHERE id = $1
    """,
        entity_list_id,
    )
    if res is None:
        raise NotFoundException(f"Entity list with id {entity_list_id} not found")

    result = EntityListSummary(
        id=entity_list_id,
        entity_list_type=res["entity_list_type"],
        label=res["label"],
    )
    query = f"""
        SELECT entity_type, count(*) as count
        FROM project_{project_name}.entity_list_items
        WHERE entity_list_id = $1
        GROUP BY entity_type;
    """
    res = await conn.fetch(query, entity_list_id)
    for row in res:
        key = f"{row['entity_type']}s"
        assert key in result.__fields__, f"Weird. {key} not in {result.__fields__}"
        setattr(result, key, row["count"])

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

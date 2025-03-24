from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.entity_lists.create_entity_list import (
    create_entity_list as _create_entity_list,
)
from ayon_server.entity_lists.create_list_item import (
    create_list_item as _create_list_item,
)
from ayon_server.entity_lists.materialize import (
    materialize_entity_list as _materialize_entity_list,
)
from ayon_server.entity_lists.models import EntityListModel
from ayon_server.entity_lists.summary import EntityListSummary, get_entity_list_summary
from ayon_server.events import EventStream
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid

from .router import router


@router.post("", status_code=201)
async def create_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    payload: EntityListModel,
    sender: Sender,
    sender_type: SenderType,
) -> EntityListSummary:
    """Create a new entity list.

    When passing list item, position field will be ignored and instead,
    the position will be determined by the order of the items in the list.
    """

    list_id = create_uuid()

    async with Postgres.acquire() as conn, conn.transaction():
        await _create_entity_list(
            project_name,
            payload.list_type,
            payload.label,
            id=list_id,
            template=payload.template,
            access=payload.access,
            attrib=payload.attrib,
            data=payload.data,
            tags=payload.tags,
            user=user,
            sender=sender,
            sender_type=sender_type,
            conn=conn,
            send_event=False,
        )

        for position, list_item in enumerate(payload.items):
            await _create_list_item(
                project_name,
                list_id,
                list_item.entity_type,
                list_item.entity_id,
                position=position,
                id=list_item.id,
                attrib=list_item.attrib,
                data=list_item.data,
                tags=list_item.tags,
                user=user,
                conn=conn,
            )
        summary = await get_entity_list_summary(conn, project_name, list_id)

    await EventStream.dispatch(
        "entity_list.created",
        description=f"Entity list '{summary['label']}' created",
        summary=dict(summary),
        project=project_name,
        user=user.name if user else None,
        sender=sender,
        sender_type=sender_type,
    )
    return summary


@router.post("/{list_id}/materialize")
async def materialize_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    sender: Sender,
    sender_type: SenderType,
) -> EntityListSummary:
    """Materialize an entity list."""

    return await _materialize_entity_list(
        project_name,
        list_id,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )


@router.patch("/{list_id}")
async def update_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
) -> EmptyResponse:
    # TODO

    return EmptyResponse()

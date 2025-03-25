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
from ayon_server.entity_lists.models import EntityListModel, EntityListPatchModel
from ayon_server.entity_lists.summary import (
    EntityListSummary,
    get_entity_list_summary,
    on_list_items_changed,
)
from ayon_server.exceptions import BadRequestException
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

    if not payload.label:
        raise BadRequestException("Label is required")

    if not payload.list_type:
        # TODO: add list type validation here
        raise BadRequestException("List type is required")

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
        )

        if payload.items:
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
            summary = await on_list_items_changed(
                conn,
                project_name,
                list_id,
                user=user,
                sender=sender,
                sender_type=sender_type,
            )
        else:
            summary = await get_entity_list_summary(conn, project_name, list_id)

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
    payload: EntityListPatchModel,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Update entity list metadata"""

    # TODO

    return EmptyResponse()

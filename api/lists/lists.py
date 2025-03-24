from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
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
) -> EntityIdResponse:
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
            conn=conn,
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

    return EntityIdResponse(id=list_id)


@router.post("/{list_id}/materialize")
async def materialize_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Materialize an entity list.

    This endpoint is used to materialize an entity list.
    """

    await _materialize_entity_list(
        project_name,
        list_id,
        user=user,
    )

    return EmptyResponse()

from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.entity_lists.entity_list import EntityList
from ayon_server.entity_lists.models import (
    EntityListItemModel,
    EntityListModel,
    EntityListPatchModel,
    EntityListPostModel,
)
from ayon_server.entity_lists.summary import (
    EntityListSummary,
)
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid

from .router import router


@router.post("", status_code=201)
async def create_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    payload: EntityListPostModel,
    sender: Sender,
    sender_type: SenderType,
) -> EntityListSummary:
    """Create a new entity list.

    When passing list item, position field will be ignored and instead,
    the position will be determined by the order of the items in the list.
    """

    list_id = payload.id or create_uuid()

    if not payload.label:
        raise BadRequestException("Label is required")

    if not payload.entity_list_type:
        raise BadRequestException("Entity list type is required")

    entity_list = await EntityList.construct(
        project_name,
        payload.entity_type,
        payload.label,
        id=list_id,
        entity_list_type=payload.entity_list_type,
        template=payload.template,
        access=payload.access,
        attrib=payload.attrib,
        data=payload.data,
        tags=payload.tags,
    )

    for item in payload.items:
        await entity_list.add(
            item.entity_id,
            id=item.id,
            position=item.position,
            label=item.label,
            attrib=item.attrib,
            data=item.data,
            tags=item.tags,
        )

    await entity_list.save()

    # summary = await on_list_items_changed(
    #     conn,
    #     project_name,
    #     list_id,
    #     user=user,
    #     sender=sender,
    #     sender_type=sender_type,
    # )

    return None
    # return summary


#
# @router.post("/{list_id}/materialize")
# async def materialize_entity_list(
#     user: CurrentUser,
#     project_name: ProjectName,
#     list_id: str,
#     sender: Sender,
#     sender_type: SenderType,
# ) -> EntityListSummary:
#     """Materialize an entity list."""
#
#     return await _materialize_entity_list(
#         project_name,
#         list_id,
#         user=user,
#         sender=sender,
#         sender_type=sender_type,
#     )


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


@router.get("/{list_id}")
async def get_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
) -> EntityListModel:
    """Get entity list

    This is for testing only. Since lists could be huge,
    it is not recommended to get them using this endpoint,

    Use GraphQL API to get the list items instead.
    """

    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute(f"SET LOCAL search_path TO project_{project_name}")
        q = "SELECT * FROM entity_lists WHERE id = $1"
        list_data = await conn.fetchrow(q, list_id)
        if list_data is None:
            raise NotFoundException(status_code=404, detail="List not found")

        result = EntityListModel(**dict(list_data), items=[])
        q = """
        SELECT * FROM entity_list_items
        WHERE entity_list_id = $1
        ORDER BY position ASC
        """
        statement = await conn.prepare(q)
        assert isinstance(result.items, list), "Items should be a list"
        async for row in statement.cursor(list_id):
            result.items.append(EntityListItemModel(**dict(row)))

    return result


@router.delete("/{list_id}")
async def delete_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
) -> EmptyResponse:
    """Delete entity list"""

    # await _delete_entity_list(project_name, list_id, user=user)
    return EmptyResponse()

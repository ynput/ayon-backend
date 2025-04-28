from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.entity_lists import EntityList
from ayon_server.entity_lists.models import (
    EntityListItemPatchModel,
    EntityListItemPostModel,
    EntityListMultiPatchItemModel,
    EntityListMultiPatchModel,
)
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres

from .router import router


@router.post("/{list_id}/items", status_code=201)
async def create_entity_list_item(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    sender: Sender,
    sender_type: SenderType,
    payload: EntityListItemPostModel,
) -> None:
    async with Postgres.acquire() as conn, conn.transaction():
        entity_list = await EntityList.load(project_name, list_id, user=user, conn=conn)
        await entity_list.ensure_can_construct()

        await entity_list.add(
            payload.entity_id,
            id=payload.id,
            position=payload.position,
            label=payload.label,
            attrib=payload.attrib,
            data=payload.data,
            tags=payload.tags,
        )
        await entity_list.save(sender=sender, sender_type=sender_type)


@router.patch("/{list_id}/items/{list_item_id}")
async def update_entity_list_item(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    list_item_id: str,
    sender: Sender,
    sender_type: SenderType,
    payload: EntityListItemPatchModel,
) -> None:
    async with Postgres.acquire() as conn, conn.transaction():
        entity_list = await EntityList.load(project_name, list_id, user=user, conn=conn)
        await entity_list.ensure_can_construct()
        item = entity_list.item_by_id(list_item_id)

        payload_dict = payload.dict(exclude_unset=True)
        await entity_list.update(
            item.id,
            **payload_dict,
            merge_fields=True,
        )
        await entity_list.save(sender=sender, sender_type=sender_type)


@router.delete("/{list_id}/items/{list_item_id}")
async def delete_entity_list_item(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    list_item_id: str,
    sender: Sender,
    sender_type: SenderType,
) -> None:
    async with Postgres.acquire() as conn, conn.transaction():
        entity_list = await EntityList.load(project_name, list_id, user=user, conn=conn)
        await entity_list.ensure_can_construct()
        await entity_list.remove(list_item_id)
        await entity_list.save(sender=sender, sender_type=sender_type)


#
# Update multiple items at once
#


async def _multi_delete(
    entity_list: EntityList,
    payload: list[EntityListMultiPatchItemModel],
) -> None:
    for item in payload:
        if item.id is None:
            continue
        await entity_list.remove(item.id)


async def _multi_replace(
    entity_list: EntityList,
    payload: list[EntityListMultiPatchItemModel],
) -> None:
    entity_list.items.clear()
    for i, item in enumerate(payload):
        if not item.entity_id:
            raise BadRequestException("Entity ID is required in replace mode")
        await entity_list.add(
            item.entity_id,
            id=item.id,
            position=i,
            label=item.label,
            attrib=item.attrib,
            data=item.data,
            tags=item.tags,
        )


async def _multi_merge(
    entity_list: EntityList,
    payload: list[EntityListMultiPatchItemModel],
) -> None:
    existing_ids = {item.id for item in entity_list.items}

    for i, item in enumerate(payload):
        if item.id in existing_ids:
            await entity_list.update(
                item.id,
                entity_id=item.entity_id,
                position=i,
                label=item.label,
                attrib=item.attrib,
                data=item.data,
                tags=item.tags,
            )

        else:
            if not item.entity_id:
                raise BadRequestException("Entity ID is required in merge mode")
            await entity_list.add(
                item.entity_id,
                id=item.id,
                position=i,
                label=item.label,
                attrib=item.attrib,
                data=item.data,
                tags=item.tags,
            )


@router.patch("/{list_id}/items")
async def update_entity_list_items(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    sender: Sender,
    sender_type: SenderType,
    payload: EntityListMultiPatchModel,
) -> None:
    async with Postgres.acquire() as conn, conn.transaction():
        entity_list = await EntityList.load(project_name, list_id, user=user, conn=conn)
        await entity_list.ensure_can_construct()

        if payload.mode == "delete":
            await _multi_delete(entity_list, payload.items)
        elif payload.mode == "replace":
            await _multi_replace(entity_list, payload.items)
        elif payload.mode == "merge":
            await _multi_merge(entity_list, payload.items)

        await entity_list.save(sender=sender, sender_type=sender_type)

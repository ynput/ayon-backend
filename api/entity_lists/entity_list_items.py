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


@router.post("/lists/{list_id}/items", status_code=201)
async def create_entity_list_item(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    sender: Sender,
    sender_type: SenderType,
    payload: EntityListItemPostModel,
) -> None:
    async with Postgres.transaction():
        entity_list = await EntityList.load(project_name, list_id, user=user)
        await entity_list.ensure_can_update()

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


@router.patch("/lists/{list_id}/items/{list_item_id}")
async def update_entity_list_item(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    list_item_id: str,
    sender: Sender,
    sender_type: SenderType,
    payload: EntityListItemPatchModel,
) -> None:
    async with Postgres.transaction():
        entity_list = await EntityList.load(project_name, list_id, user=user)
        await entity_list.ensure_can_update()
        item = entity_list.item_by_id(list_item_id)

        payload_dict = payload.dict(exclude_unset=True)
        await entity_list.update(
            item.id,
            **payload_dict,
            merge_fields=True,
        )
        await entity_list.save(sender=sender, sender_type=sender_type)


@router.delete("/lists/{list_id}/items/{list_item_id}")
async def delete_entity_list_item(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    list_item_id: str,
    sender: Sender,
    sender_type: SenderType,
) -> None:
    async with Postgres.transaction():
        entity_list = await EntityList.load(project_name, list_id, user=user)
        await entity_list.ensure_can_update()
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
            pos = i if item.position is None else item.position
            patched_fields = item.dict(exclude_unset=True).keys()
            await entity_list.update(
                item.id,
                entity_id=item.entity_id,
                position=pos,
                label=item.label if "label" in patched_fields else None,
                attrib=item.attrib if "attrib" in patched_fields else None,
                data=item.data if "data" in patched_fields else None,
                tags=item.tags if "tags" in patched_fields else None,
                normalize_positions=False,
                merge_fields=True,
            )

        else:
            if not item.entity_id:
                raise BadRequestException("Entity ID is required in for new items")
            # Append new items to the end of the list
            # until we figure out how to merge them with updates
            # We need to be explicit, because after this iteration,
            # the list will be sorted by position before pos normalization
            pos = len(entity_list.items) if item.position is None else item.position
            await entity_list.add(
                item.entity_id,
                id=item.id,
                position=pos,
                label=item.label,
                attrib=item.attrib,
                data=item.data,
                tags=item.tags,
                normalize_positions=False,
            )

    entity_list.items.sort(key=lambda item: item.position)
    entity_list.normalize_positions()


@router.patch("/lists/{list_id}/items")
async def update_entity_list_items(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    sender: Sender,
    sender_type: SenderType,
    payload: EntityListMultiPatchModel,
) -> None:
    async with Postgres.transaction():
        entity_list = await EntityList.load(project_name, list_id, user=user)
        await entity_list.ensure_can_update()

        if payload.mode == "delete":
            await _multi_delete(entity_list, payload.items)
        elif payload.mode == "replace":
            await _multi_replace(entity_list, payload.items)
        elif payload.mode == "merge":
            await _multi_merge(entity_list, payload.items)

        await entity_list.save(sender=sender, sender_type=sender_type)

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
)
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import dict_patch

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
        for key, value in payload_dict.items():
            if not hasattr(item, key):
                # Skip keys that are not attributes of the item
                continue
            if isinstance(value, dict):
                setattr(item, key, dict_patch(getattr(item, key), value))
            else:
                setattr(item, key, value)

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

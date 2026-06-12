from typing import Annotated

from ayon_server.api.dependencies import CurrentUser, EntityListID, ProjectName
from ayon_server.entity_lists import EntityList
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router


class OrderEntityListItemsRequestModel(OPModel):
    order: Annotated[
        list[str],
        Field(description="The list of item IDs in the new order", min_length=1),
    ]


@router.delete("/lists/{entity_list_id}/order")
async def order_entity_list_items(
    project_name: ProjectName,
    entity_list_id: EntityListID,
    user: CurrentUser,
    payload: OrderEntityListItemsRequestModel,
) -> None:
    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        entity_list = await EntityList.load(project_name, entity_list_id, user=user)
        await entity_list.ensure_can_update()

        # ensure the list of item IDs is the same as the current items in the list
        new_item_ids_set = set(payload.order)
        existing_item_ids_set = {item.id for item in entity_list.items}

        if new_item_ids_set != existing_item_ids_set:
            raise BadRequestException(
                "The list of item IDs must be the same as the current items in the list"
            )

        for i, item_id in enumerate(payload.order):
            entity_list.item_by_id(item_id).position = i
        entity_list.items.sort(key=lambda item: item.position)
        await entity_list.save()

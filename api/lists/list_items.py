from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.entity_lists.models import (
    EntityListItemPatchModel,
)
from ayon_server.entity_lists.update_list_item import (
    UPDATEABLE_FIELDS,
)
from ayon_server.entity_lists.update_list_item import (
    update_list_item as _update_list_item,
)
from ayon_server.exceptions import BadRequestException

from .router import router


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
    payload_dict = payload.dict(exclude_unset=True, exclude_none=True)
    for key in list(payload_dict.keys()):
        if key not in UPDATEABLE_FIELDS:
            raise BadRequestException(f"{key} cannot be updated on an entity list item")

    await _update_list_item(
        project_name,
        list_id,
        list_item_id,
        user=user,
        sender=sender,
        sender_type=sender_type,
        **payload_dict,
    )

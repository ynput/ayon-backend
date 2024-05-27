from typing import Literal

from ayon_server.api.dependencies import CurrentUser
from ayon_server.types import Field, OPModel

from .router import router


class ManageInboxItemRequest(OPModel):
    project_name: str = Field(...)

    items: list[str] = Field(
        default_factory=list,
        title="List of items",
        description="List of reference_ids of items to be managed",
    )

    status: Literal["unread", "read", "cleared"] = Field(
        ...,
        title="Status",
        description="Status to set for the items",
    )


@router.post("")
def manage_inbox_item(user: CurrentUser, request: ManageInboxItemRequest):
    # cleared: sets active to false and sets refence_data->>'read' to true
    # read: sets refence_data->>'read' to true
    # unread: sets active to true and deletes refence_data->>'read'
    pass

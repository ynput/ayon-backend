from typing import Annotated, Literal

from ayon_server.api.dependencies import CurrentUser
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router


class ManageInboxItemRequest(OPModel):
    project_name: str = Field(...)

    ids: Annotated[
        list[str] | None,
        Field(
            title="List of items",
            description="List of reference_ids of items to be managed",
        ),
    ] = None

    all: bool = Field(
        False,
        title="All",
        description="If true, all items will be managed",
    )

    status: Literal["unread", "read", "inactive"] = Field(
        ...,
        title="Status",
        description="Status to set for the items",
    )


@router.post("")
async def manage_inbox_item(user: CurrentUser, request: ManageInboxItemRequest):
    """Manage inbox items"""

    # cleared: sets active to false and sets refence_data->>'read' to true
    # read: sets refence_data->>'read' to true
    # unread: sets active to true and deletes refence_data->>'read'

    if not request.ids and not request.all:
        raise ValueError("Either ids or all should be provided")

    if request.status == "unread":
        body = "active = true, data = data - 'read'"
    elif request.status == "read":
        body = "active = true, data = jsonb_set(data, '{read}', 'true')"
    elif request.status == "inactive":
        body = "active = false, data = jsonb_set(data, '{read}', 'true')"
    else:
        raise ValueError("Invalid status. This should not happen.")

    if request.all:
        base_query = f"""
            UPDATE project_{request.project_name}.activity_references
            SET {body} WHERE entity_type = 'user' AND entity_name = $1
        """
        await Postgres.execute(base_query, user.name)
        return None

    base_query = f"""
        UPDATE project_{request.project_name}.activity_references
        SET {body}
        WHERE id = ANY($1)
        AND entity_type = 'user'
        AND entity_name = $2
    """
    await Postgres.execute(base_query, request.ids, user.name)
    return None

from typing import Annotated, Literal

from ayon_server.api.dependencies import CurrentUser
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils import SQLTool

from .router import router


class ManageInboxItemFilter(OPModel):
    active: bool | None = Field(
        None,
        title="Active",
        description="Filter by the active flag when provided",
    )
    read: bool | None = Field(
        None,
        title="Read",
        description="Filter by read state when provided",
    )
    important: bool | None = Field(
        None,
        title="Important",
        description="Filter by whether the item belongs to the Important split",
    )


class ManageInboxItemRequest(OPModel):
    project_name: str = Field(...)

    ids: Annotated[
        list[str] | None,
        Field(
            title="List of items",
            description="List of reference_ids of items to be managed",
        ),
    ] = None

    status: Literal["unread", "read", "inactive"] = Field(
        ...,
        title="Status",
        description="Status to set for the items",
    )

    item_filter: ManageInboxItemFilter | None = Field(
        None,
        title="Item filter",
        description="Optional filter selecting which inbox items should be updated",
    )


@router.post("")
async def manage_inbox_item(user: CurrentUser, request: ManageInboxItemRequest) -> None:
    """Manage inbox items"""

    # cleared: sets active to false and sets refence_data->>'read' to true
    # read: sets refence_data->>'read' to true
    # unread: sets active to true and deletes refence_data->>'read'
    if request.status == "unread":
        body = "active = true, data = data - 'read'"
    elif request.status == "read":
        body = "active = true, data = jsonb_set(data, '{read}', 'true')"
    elif request.status == "inactive":
        body = "active = false, data = jsonb_set(data, '{read}', 'true')"
    else:
        raise ValueError("Invalid status. This should not happen.")

    filter_conditions: list[str] = ["entity_type = 'user'", "entity_name = $1"]
    filter_params: list[object] = [user.name]

    def idx() -> str:
        return f"${len(filter_params)}"

    if request.ids is not None:
        filter_params.append(request.ids)
        filter_conditions.append(f"id = ANY({idx()})")

    if request.item_filter is not None:
        if request.item_filter.active is not None:
            filter_params.append(request.item_filter.active)
            filter_conditions.append(f"active = {idx()}")

        if request.item_filter.read is not None:
            filter_params.append(request.item_filter.read)
            filter_conditions.append(
                f"COALESCE((data->>'read')::boolean, false) = {idx()}"
            )

        if request.item_filter.important is not None:
            if request.item_filter.important:
                operator = "IN"
                extra_status_cond = (
                    "AND activity_id IN ("
                    f"SELECT id FROM project_{request.project_name}.activities "
                    "WHERE activity_type != 'status.change'"
                    ")"
                )
            else:
                operator = "NOT IN"
                extra_status_cond = (
                    "OR activity_id IN ("
                    f"SELECT id FROM project_{request.project_name}.activities "
                    "WHERE activity_type = 'status.change'"
                    ")"
                )

            filter_conditions.append(
                "("
                f"reference_type {operator} ('mention', 'watching') "
                f"{extra_status_cond}"
                ")"
            )

    base_query = f"""
        UPDATE project_{request.project_name}.activity_references
        SET {body}
        {SQLTool.conditions(filter_conditions)}
    """
    await Postgres.execute(base_query, *filter_params)

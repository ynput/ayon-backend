from typing import Annotated, Literal

from ayon_server.api.dependencies import CurrentUser
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

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

    itemFilter: ManageInboxItemFilter | None = Field(
        None,
        title="Item filter",
        description="Optional filter selecting which inbox items should be updated",
    )


@router.post("")
async def manage_inbox_item(user: CurrentUser, request: ManageInboxItemRequest):
    """Manage inbox items"""

    # cleared: sets active to false and sets refence_data->>'read' to true
    # read: sets refence_data->>'read' to true
    # unread: sets active to true and deletes refence_data->>'read'
    if not request.ids and not request.all and request.itemFilter is None:
        raise ValueError("Either ids or all or itemFilter should be provided")

    if request.status == "unread":
        body = "active = true, data = data - 'read'"
    elif request.status == "read":
        body = "active = true, data = jsonb_set(data, '{read}', 'true')"
    elif request.status == "inactive":
        body = "active = false, data = jsonb_set(data, '{read}', 'true')"
    else:
        raise ValueError("Invalid status. This should not happen.")

    filter_conditions: list[str] = []
    filter_params: list[object] = []
    base_param_count = 1 if request.all else 2

    if request.itemFilter is not None:
        if request.itemFilter.active is not None:
            filter_params.append(request.itemFilter.active)
            filter_conditions.append(
                f"active = ${base_param_count + len(filter_params)}"
            )

        if request.itemFilter.read is not None:
            filter_params.append(request.itemFilter.read)
            filter_conditions.append(
                "COALESCE((data->>'read')::boolean, false) = "
                f"${base_param_count + len(filter_params)}"
            )

        if request.itemFilter.important is not None:
            if request.itemFilter.important:
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

    filter_sql = ""
    if filter_conditions:
        filter_sql = "\n        AND " + "\n        AND ".join(filter_conditions)

    if request.all:
        base_query = f"""
            UPDATE project_{request.project_name}.activity_references
            SET {body}
            WHERE entity_type = 'user' AND entity_name = $1{filter_sql}
        """
        await Postgres.execute(base_query, user.name, *filter_params)
        return None

    base_query = f"""
        UPDATE project_{request.project_name}.activity_references
        SET {body}
        WHERE id = ANY($1)
        AND entity_type = 'user'
        AND entity_name = $2
        {filter_sql}
    """
    await Postgres.execute(base_query, request.ids, user.name, *filter_params)
    return None

from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import Path, Query, Request

from ayon_server.actions.config import ActionConfig
from ayon_server.actions.context import ActionContext
from ayon_server.actions.execute import ActionExecutor, ExecuteResponseModel
from ayon_server.actions.listing import (
    AvailableActionsListModel,
    get_action_whitelist,
    get_dynamic_actions,
    get_simple_actions,
)
from ayon_server.actions.manifest import BaseActionManifest
from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import AllowGuests, CurrentUser, Sender, SenderType
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router

ActionListMode = Literal["simple", "dynamic", "all"]


@router.post("/list", response_model_exclude_none=True, dependencies=[AllowGuests])
async def list_available_actions_for_context(
    context: ActionContext,
    user: CurrentUser,
    mode: ActionListMode = Query("simple", title="Action List Mode"),
    variant: str | None = Query(None, title="Settings Variant"),
) -> AvailableActionsListModel:
    """Get available actions for a context.

    This endpoint is used to get a list of actions that can be performed
    on a given context. The context is defined by the project name, entity type,
    and entity ids. The resulting list is then displayed to the user,
    who can choose to run one of the actions.

    Simple actions are actions that do not require any additional
    computation, so the list may be returned relatively quickly.

    Dynamic actions are actions that require additional computation
    to determine if they are available, so they cannot be listed as quickly as
    simple actions.

    Simple actions may be pinned to the entity sidebar.
    """

    actions = []

    if user.is_guest:
        # Guests cannot see actions, but we don't want to
        # throw 403 here
        return AvailableActionsListModel(actions=[])

    if mode == "simple":
        r = await get_simple_actions(user, context, variant)
        actions.extend(r.actions)
    elif mode == "dynamic":
        r = await get_dynamic_actions(user, context, variant)
        actions.extend(r.actions)
    elif mode == "all":
        r1 = await get_simple_actions(user, context, variant)
        actions.extend(r1.actions)
        r2 = await get_dynamic_actions(user, context, variant)
        actions.extend(r2.actions)

    for action in actions:
        if action.icon and action.icon.url:
            action.icon.url = action.icon.url.format(
                addon_url=f"/addons/{action.addon_name}/{action.addon_version}"
            )

    return AvailableActionsListModel(actions=actions)


@router.get("/manage")
async def list_all_actions(user: CurrentUser) -> list[BaseActionManifest]:
    """Get a list of all available actions.

    This endpoint is used to get a list of all available actions,
    regardless the context they are available in.
    In order to get this list, addon has to implement "get_all_actions" method.

    This endpoint is used for managing actions (e.g. enable/disable/statistics...)
    """

    if not user.is_admin:
        raise ForbiddenException("Only admins can manage actions")

    actions: list[BaseActionManifest] = []

    # TODO: from which bundle to get the actions?

    return actions


@router.post("/config")
async def configure_action(
    user: CurrentUser,
    config: ActionConfig,
    addon_name: str = Query(..., title="Addon Name", alias="addonName"),
    addon_version: str = Query(..., title="Addon Version", alias="addonVersion"),
    variant: str = Query("production", title="Action Variant"),
    identifier: str = Query(..., title="Action Identifier"),
) -> dict[str, Any]:
    addon = AddonLibrary.addon(addon_name, addon_version)
    config_dict = config.dict()
    config_value = config_dict.pop("value", None)
    context = ActionContext(**config_dict)
    if config.value is not None:
        await addon.set_action_config(
            identifier=identifier,
            context=context,
            user=user,
            variant=variant,
            config=config_value,
        )
        return config_value

    return await addon.get_action_config(
        identifier=identifier,
        context=context,
        user=user,
        variant=variant,
    )


@router.post("/execute")
async def execute_action(
    request: Request,
    user: CurrentUser,
    context: ActionContext,
    sender: Sender,
    sender_type: SenderType,
    addon_name: str = Query(..., title="Addon Name", alias="addonName"),
    addon_version: str = Query(..., title="Addon Version", alias="addonVersion"),
    variant: str = Query("production", title="Action Variant"),
    identifier: str = Query(..., title="Action Identifier"),
) -> ExecuteResponseModel:
    """Run an action.

    This endpoint is used to run an action on a context.
    This is called from the frontend when the user selects an action to run.
    """

    action_whitelist = await get_action_whitelist(user, context.project_name)
    if action_whitelist is not None:
        if identifier not in action_whitelist:
            raise ForbiddenException("You are not allowed to run this action")

    # Get access token from the Authorization header
    # to pass it to the action executor
    # to allow launcher to call the server

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise ForbiddenException("Authorization header is missing")
    access_token = auth_header.split(" ")[1]

    # Attempt to get the referer header, which is used to determine
    # the server URL to pass to the action executor
    # This is also used for launcher actions

    referer = request.headers.get("referer")
    if referer:
        parsed_url = urlparse(referer)
        server_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    else:
        server_url = "http://localhost:5000"

    # Get the addon

    # if the addon is not installed, addonlibrary raises 404
    addon = AddonLibrary.addon(addon_name, addon_version)

    # Create an action executor and run the action

    executor = ActionExecutor()
    executor.user = user
    executor.sender = sender
    executor.sender_type = sender_type
    executor.access_token = access_token
    executor.server_url = server_url
    executor.addon_name = addon_name
    executor.addon_version = addon_version
    executor.variant = variant
    executor.identifier = identifier
    executor.context = context

    return await addon.execute_action(executor)


class TakeResponseModel(OPModel):
    event_id: str = Field(
        ...,
        title="Event ID",
        example="aae4b3d4-7b7b-4b7b-8b7b-7b7b7b7b7b7b",
    )
    action_identifier: str = Field(
        ...,
        title="Action Identifier",
        example="launch-maya",
    )
    args: list[str] = Field(
        [],
        title="Action Arguments",
        example=["-file", "path/to/file.ma"],
    )
    context: ActionContext = Field(
        ...,
        title="Action Context",
    )
    addon_name: str = Field(
        ...,
        title="Addon Name",
        example="maya",
    )
    addon_version: str = Field(
        ...,
        title="Addon Version",
        example="1.5.6",
    )
    variant: str = Field(
        ...,
        title="Action Variant",
        example="production",
    )
    user_name: str = Field(
        ...,
        title="User Name",
        description="The user who initiated the action",
        example="john.doe",
    )


@router.get("/take/{token}")
async def take_action(
    token: str = Path(
        ...,
        title="Action Token",
        pattern=r"[a-f0-9]{64}",
    ),
) -> TakeResponseModel:
    """called by launcher

    This is called by the launcher when it is started via
    `ayon-launcher://action?server_url=...&token=...` URI

    Launcher connects to the server using the server url and uses the
    token to get the action event (token is the event.hash)

    The server then gets the event payload and updates the event status to in_progress
    and returns the event payload to the launcher.

    Launcher is then responsible for executing the action based on the payload
    and updating the event status to finished or failed
    """

    res = await Postgres.fetch(
        """
        SELECT * FROM events
        WHERE
            hash = $1
        AND topic = 'action.launcher'
        AND status = 'pending'
        """,
        token,
    )

    if not res:
        raise NotFoundException("Invalid token")

    event = res[0]

    # update event and set status to in_progress

    result = TakeResponseModel(
        event_id=event["id"],
        args=event["payload"].get("args", []),
        context=event["payload"].get("context", {}),
        addon_name=event["summary"].get("addon_name", ""),
        addon_version=event["summary"].get("addon_version", ""),
        variant=event["summary"].get("variant", ""),
        action_identifier=event["summary"].get("action_identifier", ""),
        user_name=event["user_name"],
    )

    await Postgres.execute(
        """
        UPDATE events SET status = 'in_progress'
        WHERE id = $1
        """,
        event["id"],
    )

    return result


class AbortRequestModel(OPModel):
    message: str = Field("Action aborted", title="Message")


@router.post("/abort/{token}")
async def abort_action(
    request: AbortRequestModel,
    token: str = Path(
        ...,
        title="Action Token",
        pattern=r"[a-f0-9]{64}",
    ),
) -> None:
    """called by launcher

    This is called by the launcher to abort an action.
    """

    res = await Postgres.fetch(
        """
        UPDATE events SET status = 'aborted', description = $2
        WHERE
            hash = $1
        AND topic = 'action.launcher'
        AND status IN ('pending', 'in_progress')
        RETURNING *
        """,
        token,
        request.message,
    )

    if not res:
        raise NotFoundException("Invalid token")

    return None

from typing import Literal
from urllib.parse import urlparse

from fastapi import Query, Request

from ayon_server.actions.context import ActionContext
from ayon_server.actions.execute import ActionExecutor, ExecuteResponseModel
from ayon_server.actions.manifest import BaseActionManifest
from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.types import Field, OPModel

from .listing import get_dynamic_actions, get_simple_actions
from .router import router

ActionListMode = Literal["simple", "dynamic", "all"]


class AvailableActionsListModel(OPModel):
    variant: str | None = Field(
        None,
        description="The variant of the bundle",
    )
    actions: list[BaseActionManifest] = Field(
        default_factory=list,
        description="The list of available actions",
    )


@router.post("list")
async def list_available_actions_for_context(
    context: ActionContext,
    user: CurrentUser,
    mode: ActionListMode = "simple",
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

    if mode in ("simple", "all"):
        r = await get_simple_actions(user, context)
        actions.extend(r.actions)
        variant = r.variant

    if mode in ("dynamic", "all"):
        r = await get_dynamic_actions(user, context)
        actions.extend(r.actions)
        variant = r.variant

    return AvailableActionsListModel(variant=variant, actions=actions)


@router.get("manage")
async def list_all_actions(user: CurrentUser) -> list[BaseActionManifest]:
    """Get a list of all available actions.

    This endpoint is used to get a list of all available actions,
    regardless the context they are available in.
    In order to get this list, addon has to implement "get_all_actions" method.

    This endpoint is used for managing actions (e.g. enable/disable/statistics...)
    """

    if not user.is_admin:
        raise ForbiddenException("Only admins can manage actions")

    actions = []

    # TODO: from which bundle to get the actions?

    return actions


@router.post("execute")
async def execute_action(
    request: Request,
    user: CurrentUser,
    context: ActionContext,
    adddon_name: str = Query(..., title="Addon Name"),
    addon_version: str = Query(..., title="Addon Version"),
    variant: str = Query("production", title="Action Variant"),
    identifier: str = Query(..., title="Action Identifier"),
) -> ExecuteResponseModel:
    """Run an action.

    This endpoint is used to run an action on a context.
    This is called from the frontend when the user selects an action to run.
    """

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

    addon = AddonLibrary.addon(adddon_name, addon_version)
    if addon is None:
        raise NotFoundException(f"Addon {adddon_name} {addon_version} not found")

    # Create an action executor and run the action

    executor = ActionExecutor()
    executor.user = user
    executor.access_token = access_token
    executor.server_url = server_url
    executor.addon_name = adddon_name
    executor.addon_version = addon_version
    executor.variant = variant
    executor.identifier = identifier
    executor.context = context

    return await addon.execute_action(executor)


@router.get("take/{event_id}")
async def take_action(event_id):
    """called by launcher

    This is called by the launcher when it is started via ayon-launcher:// uri

    Launcher connects to the server using the server url and access token
    provided in the JWT token and calls this endpoint with the event id

    The server then gets the event payload and updates the event status to in_progress
    and returns the event payload to the launcher.

    Launcher is then responsible for executing the action based on the payload
    and updating the event status to finished or failed
    """

    # query events by id
    # ensure it is an "launcher.action"

    # update event and set status to in_progress

    # return event.payload

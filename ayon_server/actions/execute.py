import urllib.parse
from typing import Annotated, Any, Literal, NotRequired, Required, TypedDict

from ayon_server.actions.context import ActionContext
from ayon_server.entities import UserEntity
from ayon_server.events import EventStream
from ayon_server.forms import SimpleForm
from ayon_server.types import Field, OPModel
from ayon_server.utils import create_hash

ResponseType = Literal[
    "simple",  # Just display a message
    "launcher",  # Open the Ayon Launcher
    "form",  # Display a form
    "redirect",  # Redirect to a different URL or open a browser tab
    "query",  # Modify the URL query parameters (web only)
]

#
# Response payloads
#


class BaseResponsePayload(TypedDict):
    """
    BaseResponsePayload defines `extra_*` fields
    that are used to pass sub-actions to the client
    such as "copy to clipboard" or "download file"
    sub-actions aren't mutually exclusive with the main action
    that is defined by the response type field and can be
    always used
    """

    extra_copy: NotRequired[str]
    extra_download: NotRequired[str]


class LauncherResponsePayload(BaseResponsePayload):
    """
    LauncherResponsePayload is used to open the Ayon Launcher
    with the given URI.
    """

    uri: Required[str]


class QueryResponsePayload(BaseResponsePayload):
    """
    QueryResponsePayload is used to modify the URL query parameters
    of the current page. This only works in the web interface.
    """

    query: Required[dict[str, str | int | float | bool]]


class RedirectResponsePayload(BaseResponsePayload):
    """
    RedirectResponsePayload is used to redirect the user
    to a different URL or open a browser tab.
    """

    uri: Required[str]
    new_tab: NotRequired[bool]


class FormResponsePayload(BaseResponsePayload):
    schema: Required[SimpleForm]
    title: Required[str]
    submit_label: NotRequired[str]
    submit_icon: NotRequired[str]
    cancel_label: NotRequired[str]
    cancel_icon: NotRequired[str]


#
# Response model
#


class ExecuteResponseModel(OPModel):
    type: Annotated[
        ResponseType,
        Field(
            description="The type of response",
            example="launcher",
        ),
    ] = "simple"

    success: Annotated[
        bool,
        Field(
            title="Action success",
            description=(
                "Payload is still parsed even if the action failed, "
                "but the message is highlighted as an error."
                "If the action execution is broken beyond repair, "
                "Raise an exception instead of returning a response."
            ),
        ),
    ] = True

    message: Annotated[
        str | None,
        Field(
            description="The message to display",
            example="Action executed successfully",
        ),
    ] = None

    payload: Annotated[
        dict[str, Any] | None,
        Field(
            title="Response payload",
            description=(
                "The payload of the response. "
                "Payload model is parsed by the client and its schema, "
                "is based on the type of action."
            ),
        ),
    ] = None


#
# Action executor class
#


class ActionExecutor:
    user: UserEntity
    server_url: str
    access_token: str | None
    addon_name: str
    addon_version: str
    variant: str
    identifier: str
    context: ActionContext

    async def get_action_config(self) -> dict[str, Any]:
        """Get action config for the given hash.

        This is used to get the action config from the database
        and return it to the user.
        """
        from ayon_server.addons.library import AddonLibrary

        addon = AddonLibrary.addon(
            self.addon_name,
            self.addon_version,
        )

        return await addon.get_action_config(
            identifier=self.identifier,
            context=self.context,
            user=self.user,
            variant=self.variant,
        )

    async def get_launcher_action_response(
        self,
        args: list[str],
        message: str | None = None,
    ) -> ExecuteResponseModel:
        """Return a response for a launcher action

        Launcher actions are actions that open the Ayon Launcher
        with the given arguments.

        An event is dispatched to the EventStream to track the progress of the action.
        The hash of the event is returned as a part of the URI.

        Uri is then used by the frontend to open the launcher.

        Launcher then uses the event hash to get the event details
        and update the event status.
        """
        payload = {
            "args": args,
            "context": self.context.dict(),
        }

        summary = {
            "addon_name": self.addon_name,
            "addon_version": self.addon_version,
            "variant": self.variant,
            "action_identifier": self.identifier,
        }

        hash = create_hash()

        await EventStream.dispatch(
            "action.launcher",
            hash=hash,
            description=message or f"Running action {self.identifier}",
            summary=summary,
            payload=payload,
            user=self.user.name,
            project=self.context.project_name,
            finished=False,
        )

        encoded_url = urllib.parse.quote_plus(self.server_url)

        return ExecuteResponseModel(
            success=True,
            type="launcher",
            message=message,
            payload={
                "uri": f"ayon-launcher://action?server_url={encoded_url}&token={hash}",
            },
        )

    async def get_server_action_response(
        self,
        success: bool = True,
        message: str | None = None,
        *,
        query_params: dict[str, Any] | None = None,
        navigate: str | None = None,
        download: str | None = None,
        copy: str | None = None,
        form: SimpleForm | None = None,
        **kwargs: Any,
    ) -> ExecuteResponseModel:
        """Return a response for a server actions

        This is a deprecated method. Use specific methods for each action type instead.
        This is provided for backward compatibility, will be removed in the future
        and it does not support all action types or features.
        """

        if message is None:
            message = f"Action {self.identifier} executed successfully"

        payload: dict[str, Any] = {**kwargs}
        response_type = "simple"

        # Mutualy exclusive action types

        if query_params:
            response_type = "query"
            payload["query"] = query_params
        elif navigate:
            response_type = "redirect"
            payload["url"] = navigate
        elif form:
            response_type = "form"
            payload["form_schema"] = list(form)
            payload["form_title"] = message

        # Sub-actions (additional behavior of the response)
        # Such as "copy somethig to clipboard"

        if copy:
            payload["extra_copy"] = copy
        if download:
            payload["extra_download"] = download

        return ExecuteResponseModel(
            success=success,
            type=response_type,
            message=message,
            payload=payload,
        )

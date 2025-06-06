import urllib.parse
from typing import Annotated, Any, Literal, NotRequired, Required, TypedDict

from ayon_server.actions.context import ActionContext
from ayon_server.entities import UserEntity
from ayon_server.events import EventStream
from ayon_server.forms import SimpleForm
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.utils import create_hash

ResponseType = Literal[
    "form",
    "launcher",
    "navigate",
    "query",
    "redirect",
    "simple",
]

#
# Response payloads
#


class SimpleResponsePayload(TypedDict):
    """
    BaseResponsePayload defines `extra_*` fields
    that are used to pass sub-actions to the client
    such as "copy to clipboard" or "download file"
    sub-actions aren't mutually exclusive with the main action
    that is defined by the response type field and can be
    always used
    """

    extra_clipboard: NotRequired[str]  # Text to copy to clipboard
    extra_download: NotRequired[str]  # URL to download
    extra_reload: NotRequired[list[str]]  # List of tags to invalidate


class FormResponsePayload(SimpleResponsePayload):
    """
    FormResponsePayload is used to display a form
    and get the input from the user.

    When the form is submitted, the input is sent back to the server.
    """

    title: Required[str]  # Form title (header)
    fields: Required[SimpleForm]
    submit_label: NotRequired[str | None]
    submit_icon: NotRequired[str]
    cancel_label: NotRequired[str | None]
    cancel_icon: NotRequired[str]


class LauncherResponsePayload(SimpleResponsePayload):
    """
    LauncherResponsePayload is used to open the Ayon Launcher
    with the given URI.

    Example:
    ```
    uri="ayon-launcher://action?server_url=https%3A%2F%2Fexample.com&token=hash"
    ```
    """

    uri: Required[str]


class NavigateResponsePayload(SimpleResponsePayload):
    """
    NavigateResponsePayload is used to soft-navigate the user
    to a relative URL within the Ayon web interface.

    Example:
    ```
    uri="/projects/AY_CG_demo/overview"
    ```
    """

    uri: Required[str]


class QueryResponsePayload(SimpleResponsePayload):
    """
    QueryResponsePayload is used to modify the URL query parameters
    of the current page. This only works in the web interface.
    """

    query: Required[dict[str, str | int | float | bool]]


class RedirectResponsePayload(SimpleResponsePayload):
    """
    RedirectResponsePayload is used to redirect the user
    to a different URL or open a new browser tab.

    Example:
    ```
    uri="https://example.com"
    new_tab=true
    ```
    """

    uri: Required[str]
    new_tab: NotRequired[bool]


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
    sender: str | None = None
    sender_type: str | None = None

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

    #
    # Response getters
    #
    # TODO: After upgrading to Python 3.12, use unpacked kwargs for the payload
    # Then we'l be also able to get rid of checking for `extra_*` fields
    #

    async def get_launcher_response(
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

    async def get_simple_response(
        self,
        message: str | None = "Action executed successfully",
        success: bool = True,
        extra_clipboard: str | None = None,
        extra_download: str | None = None,
        **kwargs: Any,
    ) -> ExecuteResponseModel:
        """Return a simple response with a message"""
        payload: dict[str, Any] = {**kwargs}
        if extra_clipboard:
            payload["extra_clipboard"] = extra_clipboard
        if extra_download:
            payload["extra_download"] = extra_download
        return ExecuteResponseModel(
            success=success,
            type="simple",
            message=message,
            payload=payload,
        )

    async def get_navigate_response(
        self,
        uri: str,
        message: str | None = None,
        success: bool = True,
        extra_clipboard: str | None = None,
        extra_download: str | None = None,
        **kwargs: Any,
    ) -> ExecuteResponseModel:
        """Return a response for a redirect action"""
        payload: dict[str, Any] = {"uri": uri, **kwargs}
        if extra_clipboard:
            payload["extra_clipboard"] = extra_clipboard
        if extra_download:
            payload["extra_download"] = extra_download

        return ExecuteResponseModel(
            success=success,
            type="navigate",
            message=message,
            payload=payload,
        )

    async def get_redirect_response(
        self,
        uri: str,
        new_tab: bool = False,
        message: str | None = None,
        success: bool = True,
        extra_clipboard: str | None = None,
        extra_download: str | None = None,
        **kwargs: Any,
    ) -> ExecuteResponseModel:
        """Return a response for a redirect action"""
        payload: dict[str, Any] = {
            "uri": uri,
            "new_tab": new_tab,
            **kwargs,
        }
        if extra_clipboard:
            payload["extra_clipboard"] = extra_clipboard
        if extra_download:
            payload["extra_download"] = extra_download

        return ExecuteResponseModel(
            success=success,
            type="redirect",
            message=message,
            payload=payload,
        )

    async def get_query_response(
        self,
        query: dict[str, str | int | float | bool],
        message: str | None = None,
        success: bool = True,
        extra_clipboard: str | None = None,
        extra_download: str | None = None,
        **kwargs: Any,
    ) -> ExecuteResponseModel:
        """Return a response for a query action"""
        payload: dict[str, Any] = {"query": query, **kwargs}
        if extra_clipboard:
            payload["extra_clipboard"] = extra_clipboard
        if extra_download:
            payload["extra_download"] = extra_download
        return ExecuteResponseModel(
            success=success,
            type="query",
            message=message,
            payload=payload,
        )

    async def get_form_response(
        self,
        title: str,
        fields: SimpleForm,
        submit_label: str | None = "Submit",
        submit_icon: str = "check",
        cancel_label: str | None = "Cancel",
        cancel_icon: str = "close",
        message: str | None = None,
        success: bool = True,
        extra_clipboard: str | None = None,
        extra_download: str | None = None,
        **kwargs: Any,
    ) -> ExecuteResponseModel:
        """Return a response for a form action"""
        payload = {
            "title": title,
            "fields": list(fields),
            "submit_label": submit_label,
            "submit_icon": submit_icon,
            "cancel_label": cancel_label,
            "cancel_icon": cancel_icon,
            **kwargs,
        }
        if extra_clipboard:
            payload["extra_clipboard"] = extra_clipboard
        if extra_download:
            payload["extra_download"] = extra_download
        return ExecuteResponseModel(
            success=success,
            type="form",
            message=message,
            payload=payload,
        )

    #
    # Deprecated methods
    #

    async def get_launcher_action_response(
        self,
        args: list[str],
        message: str | None = None,
    ) -> ExecuteResponseModel:
        """Deprecated alias for get_launcher_response"""
        logger.debug(
            "get_launcher_action_response is deprecated. "
            "Use get_launcher_response instead"
        )
        return await self.get_launcher_response(
            args=args,
            message=message,
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
        """Deprecated: Return a response for a server actions

        This is a deprecated method. Use specific methods for each action type instead.
        This is provided for backward compatibility, will be removed in the future
        and it does not support all action types or features.
        """

        logger.debug(
            "get_launcher_action_response is deprecated. "
            "Use explicit get_*_response method instead"
        )

        if message is None:
            message = f"Action {self.identifier} executed successfully"

        payload: dict[str, Any] = {**kwargs}
        response_type = "simple"

        # Mutually exclusive action types

        if query_params:
            response_type = "query"
            payload["query"] = query_params
        elif navigate:
            response_type = "redirect"
            payload["uri"] = navigate
        elif form:
            response_type = "form"
            payload["fields"] = list(form)
            payload["title"] = message
            payload["submit_label"] = "Submit"
            payload["submit_icon"] = "check"
            payload["cancel_label"] = "Cancel"
            payload["cancel_icon"] = "close"

        # Sub-actions (additional behavior of the response)
        # Such as "copy somethig to clipboard"

        if copy:
            payload["extra_clipboard"] = copy
        if download:
            payload["extra_download"] = download

        return ExecuteResponseModel(
            success=success,
            type=response_type,
            message=message,
            payload=payload,
        )

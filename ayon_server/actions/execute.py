import urllib.parse
from typing import Any, Literal

from ayon_server.actions.context import ActionContext
from ayon_server.entities import UserEntity
from ayon_server.events import EventStream
from ayon_server.types import Field, OPModel
from ayon_server.utils import create_hash


class ExecuteResponseModel(OPModel):
    type: Literal["launcher", "server"] = Field(
        ...,
        description="The type of response",
        example="launcher",
    )
    success: bool = Field(
        True,
        description="Whether the action was successful",
    )
    message: str | None = Field(
        None,
        description="The message to display",
        example="Action executed successfully",
    )

    uri: str | None = Field(
        None,
        description="The uri to call from the browser",
        example="ayon-launcher://action?server_url=http%3A%2F%2Flocalhost%3A8000%2F&token=eyJaaaa",
    )

    payload: dict[str, Any] | None = Field(
        None,
        description="The payload of the request",
    )


class ActionExecutor:
    user: UserEntity
    server_url: str
    access_token: str | None
    addon_name: str
    addon_version: str
    variant: str
    identifier: str
    context: ActionContext

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
            uri=f"ayon-launcher://action?server_url={encoded_url}&token={hash}",
            message=message,
        )

    async def get_server_action_response(
        self,
        success: bool = True,
        message: str | None = None,
        **kwargs: Any,
    ) -> ExecuteResponseModel:
        """Return a response for a server actions

        Server actions are actions that are only executed on the server.
        They only return a message to display in the frontend
        after the action is executed.
        """

        if message is None:
            message = f"Action {self.identifier} executed successfully"

        return ExecuteResponseModel(
            success=success,
            type="server",
            message=message,
            payload=kwargs,
        )

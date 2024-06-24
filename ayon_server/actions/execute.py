import time
from typing import Literal

import jwt

from ayon_server.actions.context import ActionContext
from ayon_server.entities import UserEntity
from ayon_server.events import EventStream
from ayon_server.types import Field, OPModel


class ExecuteResponseModel(OPModel):
    type: Literal["launcher", "void"] = Field(...)
    message: str | None = Field(None, description="The message to display")
    uri: str | None = Field(None, description="The url to open in the browser")

    # TODO: for http/browser actions
    # payload: dict | None = Field(None, description="The payload of the request")


class ActionExecutor:
    user: UserEntity
    server_url: str
    access_token: str | None
    addon_name: str
    addon_version: str
    variant: str
    identifier: str
    context: ActionContext

    async def get_launcher_action(
        self,
        args: list[str],
        message: str | None = None,
    ) -> ExecuteResponseModel:
        payload = {
            "args": args,
            "variant": self.variant,
        }

        summary = {
            "addon_name": self.addon_name,
            "addon_version": self.addon_version,
            "variant": self.variant,
            "action_identifier": self.identifier,
        }

        event_id = await EventStream.dispatch(
            "action.launcher",
            description=message or "Running action",
            summary=summary,
            payload=payload,
            user=self.user.name,
            project=self.context.project_name,
            finished=False,
        )

        token = jwt.encode(
            {
                "jti": event_id,
                "aud": self.server_url,
                "iat": time.time(),
                "exp": time.time() + 60,
                "sub": self.access_token,
            },
            "secret",
            algorithm="HS256",
        )

        return ExecuteResponseModel(
            type="launcher",
            uri=f"ayon-launcher://action?token={token}",
            message=message,
        )

    def get_void_action(self, message: str | None = None) -> ExecuteResponseModel:
        return ExecuteResponseModel(type="void", message=message)

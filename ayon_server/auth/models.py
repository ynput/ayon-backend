from typing import Annotated

from pydantic import Field

from ayon_server.entities import UserEntity
from ayon_server.types import OPModel


class LoginResponseModel(OPModel):
    detail: Annotated[
        str | None,
        Field(
            title="Detail message",
            description="Text message, which may be displayed to the user",
            example="Logged in as NAME",
        ),
    ] = None

    error: Annotated[
        str | None,
        Field(
            example="Unauthorized",
        ),
    ] = None

    token: Annotated[
        str | None,
        Field(
            title="Access token",
            example="TOKEN",
        ),
    ] = None

    user: Annotated[
        UserEntity.model.main_model | None,  # type: ignore
        Field(title="User data"),
    ] = None

    redirect_to: Annotated[
        str | None,
        Field(
            title="Redirect URL",
            description="URL to redirect the user after login",
            example="/projects",
        ),
    ] = None


class LogoutResponseModel(OPModel):
    detail: Annotated[
        str,
        Field(
            title="Response detail",
            description="Text description, which may be displayed to the user",
            example="Logged out",
        ),
    ] = "Logged out"

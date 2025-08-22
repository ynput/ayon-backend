from typing import Annotated

from pydantic import Field

from ayon_server.entities import UserEntity
from ayon_server.types import OPModel

UserMainModel = UserEntity.model.main_model  # noqa


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

    user: Annotated[UserMainModel | None, Field(title="User data")] = None  # type: ignore

    redirect_url: Annotated[
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

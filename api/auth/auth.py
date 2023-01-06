"""API endpoints related to an user authentication.

 - Login using username/password credentials
 - Logout (revoke access token)

Login using Oauth2 is implemented in the oauth module.
"""

from fastapi import Depends, Request

from ayon_server.api import ResponseFactory
from ayon_server.api.dependencies import dep_access_token
from ayon_server.auth.password import PasswordAuth
from ayon_server.auth.session import Session
from ayon_server.entities import UserEntity
from ayon_server.exceptions import UnauthorizedException
from ayon_server.types import Field, OPModel

from .router import router


class LoginRequestModel(OPModel):
    name: str = Field(
        ...,
        title="User name",
        description="Username",
        example="admin",
    )
    password: str = Field(
        ...,
        title="Password",
        description="Password",
        example="SecretPassword.123",
    )


class LoginResponseModel(OPModel):
    detail: str = Field(
        ...,
        title="Response detail",
        description="Text description, which may be displayed to the user",
        example="Logged in as USERNAME",
    )
    token: str = Field(
        ...,
        title="Access token",
        example="ACCESS_TOKEN",
    )
    user: UserEntity.model.main_model  # type: ignore


@router.post(
    "/login",
    response_model=LoginResponseModel,
    responses={401: ResponseFactory.error(401, "Unable to log in")},
)
async def login(request: Request, login: LoginRequestModel):
    """Login using name/password credentials.

    Returns access token and user information. The token is used for
    authentication in other endpoints. It is valid for 24 hours,
    but it is extended automatically when the user is active.

    Token may be revoked by calling the logout endpoint or using
    session manager.

    Returns 401 response if the credentials are invalid.
    """

    if not (session := await PasswordAuth.login(login.name, login.password, request)):
        # We don't need to be too verbose about the bad credentials
        raise UnauthorizedException("Invalid login/password")

    return LoginResponseModel(
        detail=f"Logged in as {session.user.name}",
        token=session.token,
        user=session.user,
    )


#
# [POST] /auth/logout
#


class LogoutResponseModel(OPModel):
    detail: str = Field(
        "Logged out",
        title="Response detail",
        description="Text description, which may be displayed to the user",
        example="Logged out",
    )


@router.post(
    "/logout",
    response_model=LogoutResponseModel,
    responses={401: ResponseFactory.error(401, "Not logged in")},
)
async def logout(access_token: str = Depends(dep_access_token)):
    """Log out the current user."""
    await Session.delete(access_token)
    return LogoutResponseModel()

"""API endpoints related to a user authentication. (excluding SSO)

 - Login using username/password credentials
 - Logout (revoke access token)
"""

from fastapi import Request

from ayon_server.api.dependencies import AccessToken
from ayon_server.auth.models import LoginResponseModel, LogoutResponseModel
from ayon_server.auth.password import PasswordAuth
from ayon_server.auth.session import Session
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


@router.post("/login")
async def login(request: Request, login: LoginRequestModel) -> LoginResponseModel:
    """Login using name/password credentials.

    Returns access token and user information. The token is used for
    authentication in other endpoints. It is valid for 24 hours,
    but it is extended automatically when the user is active.

    Token may be revoked by calling the logout endpoint or using
    session manager.

    Returns 401 response if the credentials are invalid.
    """

    session = await PasswordAuth.login(login.name, login.password, request)

    return LoginResponseModel(
        detail=f"Logged in as {session.user.name}",
        token=session.token,
        user=session.user,
    )


@router.post("/logout")
async def logout(access_token: AccessToken) -> LogoutResponseModel:
    """Log out the current user."""
    await Session.delete(access_token)
    return LogoutResponseModel()

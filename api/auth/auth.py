"""API endpoints related to a user authentication. (excluding SSO)

- Login using username/password credentials
- Logout (revoke access token)
"""

from fastapi import Request

from ayon_server.api.dependencies import AccessToken, AllowGuests, CurrentUserOptional
from ayon_server.auth.models import LoginResponseModel, LogoutResponseModel
from ayon_server.auth.password import PasswordAuth
from ayon_server.auth.session import Session
from ayon_server.auth.tokenauth import handle_token_auth_callback
from ayon_server.exceptions import BadRequestException
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


@router.get("/tokenauth", dependencies=[AllowGuests])
async def token_auth_callback(
    request: Request, current_user: CurrentUserOptional
) -> LoginResponseModel:
    """Callback for token authentication.

    This endpoint is used to handle the callback from the token
    authentication flow. It is not intended to be called directly.
    """
    data = dict(request.query_params)
    token = data.get("q")
    if not token:
        raise BadRequestException("Missing 'q' query parameter with token")

    return await handle_token_auth_callback(token, request, current_user)

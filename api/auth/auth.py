"""API endpoints related to an user authentication.

 - Login using username/password credentials
 - Logout (revoke access token)

Login using Oauth2 is implemented in the oauth module.
"""

from fastapi import APIRouter, Depends

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_access_token
from openpype.auth.password import PasswordAuth
from openpype.auth.session import Session
from openpype.entities import UserEntity
from openpype.exceptions import UnauthorizedException
from openpype.types import Field, OPModel

#
# Router
#


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


#
# [POST] /auth/login
#


class LoginRequestModel(OPModel):
    name: str = Field(..., description="Username", example="admin")
    password: str = Field(..., description="Password", example="SecretPassword.123")


class LoginResponseModel(OPModel):
    detail: str = "Logged in as NAME"
    token: str = "ACCESS_TOKEN"
    user: UserEntity.model.main_model  # type: ignore


@router.post(
    "/login",
    response_model=LoginResponseModel,
    responses={401: ResponseFactory.error(401, "Unable to log in")},
)
async def login(login: LoginRequestModel):
    """Login using name/password credentials.

    Check provided credentials and return an access token
    for secure requests and the user information.
    """

    if not (session := await PasswordAuth.login(login.name, login.password)):
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
    detail: str = "Logged out"


@router.post(
    "/logout",
    response_model=LogoutResponseModel,
    responses={401: ResponseFactory.error(401, "Not logged in")},
)
async def logout(access_token: str = Depends(dep_access_token)):
    """Log out the current user."""
    await Session.delete(access_token)
    return LogoutResponseModel()

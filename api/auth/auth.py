"""API endpoints related to an user authentication.

 - Login using username/password credentials
 - Logout (revoke access token)

Login using Oauth2 is implemented in the oauth module.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from openpype.api import ResponseFactory, APIException
from openpype.api.dependencies import dep_access_token
from openpype.entities import UserEntity
from openpype.auth.password import PasswordAuth
from openpype.auth.session import Session


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


class LoginRequestModel(BaseModel):
    name: str
    password: str


class LoginResponseModel(BaseModel):
    detail: str = "Logged in as NAME"
    token: str = "ACCESS_TOKEN"
    user: UserEntity.model()


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
        raise APIException(401, "Invalid login/password")

    return LoginResponseModel(
        detail=f"Logged in as {session.user_entity.name}",
        token=session.token,
        user=session.user,
    )


#
# [POST] /auth/logout
#


class LogoutResponseModel(BaseModel):
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

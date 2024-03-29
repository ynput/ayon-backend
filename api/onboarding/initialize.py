from fastapi import Request

from ayon_server.auth.models import LoginResponseModel
from ayon_server.auth.session import Session
from ayon_server.entities import UserEntity
from ayon_server.exceptions import UnauthorizedException
from ayon_server.helpers.setup import admin_exists
from ayon_server.types import Field, OPModel

from .router import router


class InitializeRequestModel(OPModel):
    # Admin prefix in the field names allows
    # extending this model with more fields
    # such as basic backend configuration in the future

    admin_name: str = Field(
        ...,
        title="User name",
        description="Username",
        example="admin",
    )
    admin_password: str = Field(
        ...,
        title="Password",
        description="Password",
        example="SecretPassword.123",
    )
    admin_full_name: str = Field(
        "",
        title="Full name",
        description="Full name",
        example="Administrator",
    )
    admin_email: str = Field(
        "",
        title="Administrator email",
        example="admin@example.com",
    )


@router.post("/initialize")
async def create_first_admin(
    request: Request,
    payload: InitializeRequestModel,
) -> LoginResponseModel:
    """Create the first user and log in.

    When Ayon is started for the first time, there is no admin user.
    in that case `/api/system/info` contains `{"noAdmin_user": true}`.

    The frontend will display a form to create the first admin user.
    using this endpoint. It will also log in the user and return the same
    response as `/api/auth/login`, so the frontend can continue in
    logged-in mode.
    """

    if await admin_exists():
        raise UnauthorizedException("Admin already initialized")

    user = UserEntity(
        payload={
            "name": payload.admin_name,
            "attrib": {
                "email": payload.admin_email,
                "fullName": payload.admin_full_name,
            },
            "data": {
                "isAdmin": True,
            },
        }
    )
    user.set_password(payload.admin_password)
    await user.save()
    session = await Session.create(user, request)
    return LoginResponseModel(
        detail=f"Logged in as {session.user.name}",
        token=session.token,
        user=session.user,
    )

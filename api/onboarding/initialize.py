from fastapi import Request

from ayon_server.auth.models import LoginResponseModel
from ayon_server.auth.session import Session
from ayon_server.entities import UserEntity
from ayon_server.exceptions import UnauthorizedException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router


class InitializeRequestModel(OPModel):
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


async def admin_exists() -> bool:
    async for row in Postgres.iterate(
        "SELECT name FROM users WHERE data->>'isAdmin' = 'true'"
    ):
        return True
    return False


@router.post("/initialize")
async def create_first_admin(
    request: Request,
    payload: InitializeRequestModel,
) -> LoginResponseModel:
    """Create the first user and log in."""

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
                "isAdmin": "true",
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

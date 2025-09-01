import time

from ayon_server.auth.models import LoginResponseModel
from ayon_server.auth.session import Session
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.utils import create_hash

from .router import router

TOKEN_TTL = 3600
PASSWORD_RESET_EMAIL_TEMPLATE_PLAIN = """
Hello {name},
it seems that you have requested a password reset for your account for Ayon.
Please follow this link to reset your password:

{reset_url}?token={token}
"""

PASSWORD_RESET_EMAIL_TEMPLATE_HTML = """
<p>Hello, {name}</p>

<p>it seems that you have requested a password reset for your account for Ayon.
Please follow this link to reset your password:</p>

<p><a href="{reset_url}?token={token}">Reset password</a></p>
"""


class PasswordResetRequestModel(OPModel):
    email: str = Field(..., title="Email", example="you@somewhere.com")
    url: str = Field(...)


@router.post("/passwordResetRequest")
async def password_reset_request(request: PasswordResetRequestModel):
    query = "SELECT name, data FROM users WHERE LOWER(attrib->>'email') = $1"
    res = await Postgres.fetchrow(query, request.email.lower())
    if res is None:
        logger.error(
            f"Attempted password reset using non-existent email: {request.email}"
        )
        return

    user_data = res["data"]

    password_reset_request = user_data.get("passwordResetRequest")
    if password_reset_request:
        password_request_time = password_reset_request.get("time", 0)
        if password_request_time and (time.time() - password_request_time) < 600:
            logger.error(
                "Attempted password reset too soon "
                f"after previous attempt for {request.email}"
            )
            msg = "Attempted password reset too soon after previous attempt"
            raise ForbiddenException(msg)

    token = create_hash()
    password_reset_request = {
        "time": time.time(),
        "token": token,
    }

    user = await UserEntity.load(res["name"])
    user.data["passwordResetRequest"] = password_reset_request

    tplvars = {
        "token": token,
        "reset_url": request.url,
        "name": user.attrib.fullName or user.name,
    }

    await user.save()
    await user.send_mail(
        "Ayon password reset",
        text=PASSWORD_RESET_EMAIL_TEMPLATE_PLAIN.format(**tplvars),
        html=PASSWORD_RESET_EMAIL_TEMPLATE_HTML.format(**tplvars),
    )
    logger.info(f"Sent password reset email to {request.email}")


class PasswordResetModel(OPModel):
    token: str = Field(..., title="Token")
    password: str | None = Field(None, title="New password")


@router.post("/passwordReset")
async def password_reset(request: PasswordResetModel) -> LoginResponseModel:
    query = (
        "SELECT name, data FROM users WHERE data->'passwordResetRequest'->>'token' = $1"
    )

    ERROR_MESSAGE = "Invalid reset token or token has expired"

    res = await Postgres.fetchrow(query, request.token)
    if res is None:
        logger.error("Attempted password reset using invalid token")
        raise ForbiddenException(ERROR_MESSAGE)

    user_name = res["name"]
    user_data = res["data"]

    password_reset_request = user_data.get("passwordResetRequest", {})
    password_request_time = password_reset_request.get("time", None)

    if not password_request_time or (time.time() - password_request_time) > TOKEN_TTL:
        logger.error("Attempted password reset using expired token")
        raise ForbiddenException(ERROR_MESSAGE)

    if request.password is None:
        # just checking whether the token is valid
        # we don't set the password
        return LoginResponseModel(detail="Token is valid")

    user = await UserEntity.load(user_name)
    user.data["passwordResetRequest"] = None
    user.set_password(request.password, complexity_check=True)
    await user.save()

    session = await Session.create(user)
    return LoginResponseModel(
        detail="Password changed",
        token=session.token,
        user=session.user,
    )

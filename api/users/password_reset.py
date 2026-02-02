import secrets
import time
from typing import Annotated

from fastapi import Request

from ayon_server.auth.models import LoginResponseModel
from ayon_server.auth.session import Session
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.email import EmailTemplate
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.utils.server import server_url_from_request

from .router import router

TOKEN_TTL = 3600


class PasswordResetRequestModel(OPModel):
    email: Annotated[str, Field(title="Email", example="you@somewhere.com")]
    # url: Annotated[str, Field(title="Password reset URL")]


@router.post("/passwordResetRequest")
async def password_reset_request(payload: PasswordResetRequestModel, request: Request):
    query = "SELECT name, data FROM users WHERE LOWER(attrib->>'email') = $1"
    res = await Postgres.fetchrow(query, payload.email.lower())
    if res is None:
        logger.error(
            f"Attempted password reset using non-existent email: {payload.email}"
        )
        return

    user_data = res["data"]

    password_reset_request = user_data.get("passwordResetRequest")
    if password_reset_request:
        password_request_time = password_reset_request.get("time", 0)
        if password_request_time and (time.time() - password_request_time) < 600:
            logger.error(
                "Attempted password reset too soon "
                f"after previous attempt for {payload.email}"
            )
            msg = "Attempted password reset too soon after previous attempt"
            raise ForbiddenException(msg)

    token = secrets.token_urlsafe(32)
    password_reset_request = {
        "time": time.time(),
        "token": token,
    }

    user = await UserEntity.load(res["name"])
    user.data["passwordResetRequest"] = password_reset_request
    server_url = server_url_from_request(request)

    tplvars = {
        "reset_url": f"{server_url}/passwordReset?token={token}",
        "full_name": user.attrib.fullName or user.name,
    }

    template = EmailTemplate()
    body = await template.render_template("password_reset.jinja", tplvars)
    subject = "Ayon password reset request"

    await user.save()
    await user.send_mail(
        subject=subject,
        html=body,
    )
    logger.info(f"Sent password reset email to {payload.email}")


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

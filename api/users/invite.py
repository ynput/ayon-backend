import secrets
import time
from typing import Annotated

from fastapi import Request

from ayon_server.api.dependencies import CurrentUser, UserName
from ayon_server.auth.models import LoginResponseModel
from ayon_server.auth.session import Session
from ayon_server.config.serverconfig import get_server_config
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.email import EmailTemplate
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.utils.server import server_url_from_request

from .router import router

TOKEN_TTL = 3600 * 24 * 7  # 7 days


class InviteUserRequest(OPModel):
    message: Annotated[
        str | None,
        Field(title="Message", example="Hi, please join our Ayon server!"),
    ] = None


@router.post("/{user_name}/invite")
async def invite_user(
    current_user: CurrentUser,
    user_name: UserName,
    payload: InviteUserRequest,
    request: Request,
):
    if not current_user.is_manager:
        raise ForbiddenException("Only managers and administrators can invite users")

    user = await UserEntity.load(user_name)

    server_url = server_url_from_request(request)
    server_config = await get_server_config()
    password_enabled = (not server_config.authentication.hide_password_auth) and (
        not user.data.get("disablePasswordLogin", False)
    )
    studio_name = server_config.studio_name

    token = secrets.token_urlsafe(32)
    invite_request = {
        "time": time.time(),
        "token": token,
    }
    user.data["inviteRequest"] = invite_request
    user.data.pop("inviteAcceptedAt", None)

    accept_link = (
        f"{server_url}/acceptInvite?token={token}"
        if password_enabled
        else f"{server_url}/"
    )

    tplvars = {
        "accept_link": accept_link,
        "full_name": user.attrib.fullName or user.name,
        "studio_name": studio_name,
        "user_name": user.name,
        "password_enabled": password_enabled,
    }

    template = EmailTemplate()
    body = await template.render_template(
        "user_invite.jinja",
        tplvars,
        base_url=server_url,
    )

    subject = f"You have been invited to join {studio_name} Ayon server"

    await user.save()
    await user.send_mail(
        subject=subject,
        html=body,
    )
    logger.info(f"Sent invitation email to {user.attrib.email}")


class AcceptInviteRequest(OPModel):
    token: str = Field(..., title="Token")
    password: str | None = Field(None, title="New password")


@router.post("/acceptInvite")
async def accept_invite(
    payload: AcceptInviteRequest, request: Request
) -> LoginResponseModel:
    query = "SELECT name, data FROM users WHERE data->'inviteRequest'->>'token' = $1"

    ERROR_MESSAGE = "Invalid invite token or token has expired"

    res = await Postgres.fetchrow(query, payload.token)
    if res is None:
        logger.error("Attempted accept invite using invalid token")
        raise ForbiddenException(ERROR_MESSAGE)

    user_name = res["name"]
    user_data = res["data"]

    invite_request = user_data.get("inviteRequest", {})
    invite_request_time = invite_request.get("time") or 0

    if time.time() - invite_request_time > TOKEN_TTL:
        raise ForbiddenException(ERROR_MESSAGE)

    if payload.password is None:
        # just checking whether the token is valid
        # we don't set the password
        return LoginResponseModel(detail="Token is valid")

    user = await UserEntity.load(user_name)
    user.set_password(payload.password, complexity_check=True)

    # No need to save here, because save is called in Session.create
    # upon removing inviteRequest from user data
    # await user.save()

    session = await Session.create(user, request=request)
    return LoginResponseModel(
        detail="Password changed",
        token=session.token,
        user=session.user,
    )

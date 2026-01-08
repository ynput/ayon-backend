from typing import Any

from fastapi import Request

from ayon_server.auth.session import Session
from ayon_server.entities import UserEntity
from ayon_server.exceptions import (
    BadRequestException,
    InvalidSettingsException,
    UnauthorizedException,
)
from ayon_server.helpers.crypto import decrypt_json_urlsafe, encrypt_json_urlsafe
from ayon_server.helpers.email import EmailTemplate, is_mailing_enabled, send_mail
from ayon_server.helpers.guest_users import GuestUsers
from ayon_server.logging import log_traceback, logger
from ayon_server.types import OPModel
from ayon_server.utils import server_url_from_request, slugify

from .models import LoginResponseModel


class TokenPayload(OPModel):
    email: str
    is_guest: bool = True
    subject: str | None = None
    project_name: str | None = None
    full_name: str | None = None
    redirect_url: str | None = None


async def send_invite_email(
    email: str,
    base_url: str,
    body_template: str,
    *,
    full_name: str | None = None,
    subject: str | None = None,
    is_guest: bool = True,
    project_name: str | None = None,
    redirect_url: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    if not await is_mailing_enabled():
        raise InvalidSettingsException("Mailing is not enabled.")

    payload = TokenPayload(
        email=email,
        full_name=full_name,
        is_guest=is_guest,
        project_name=project_name,
        redirect_url=redirect_url,
        subject=subject,
    )

    enc_data = await encrypt_json_urlsafe(payload.dict(exclude_none=True))
    token = enc_data.token
    await enc_data.set_nonce(ttl=3600 * 24)

    ctx = {
        "full_name": full_name or "User",
        "email": email,
        "project_name": project_name or "the project",
        "invite_link": f"{base_url}/login/_token?q={token}",
        "redirect_url": redirect_url or "/",
    }
    if context:
        ctx.update(context)

    template = EmailTemplate()
    body = await template.render(body_template, ctx)
    subject = subject or "Invitation to Ayon instance"

    logger.debug(f"Sending guest invite to {email}: redirect to {redirect_url}")
    await send_mail([email], subject, html=body)


async def send_extend_email(payload: TokenPayload, base_url: str) -> None:
    """Send an email to the user to extend their invite link.

    When a link is used for the first time to log in, it is invalidated.
    It still contain the original payload, so it "knows" where to take the user
    but in order to get the users session, user must get a new link.

    This is done automatically, when an expired link is used.
    """

    if not await is_mailing_enabled():
        raise InvalidSettingsException("Mailing is not enabled.")

    enc_data = await encrypt_json_urlsafe(payload.dict(exclude_none=True))
    token = enc_data.token
    await enc_data.set_nonce(ttl=3600 * 24)

    ctx = {
        "full_name": payload.full_name or "User",
        "email": payload.email,
        "project_name": payload.project_name or "the project",
        "invite_link": f"{base_url}/login/_token?q={token}",
        "redirect_url": payload.redirect_url or "/",
    }

    template = EmailTemplate()
    body = await template.render_template("token_renew.jinja", ctx)
    subject = payload.subject or "Ayon access link renewal"
    logger.debug(
        f"Sending guest exted email to {payload.email}: "
        "redirect to {payload.redirect_url}"
    )
    await send_mail([payload.email], subject, html=body)


async def create_guest_user_session(
    email: str,
    request: Request,
    *,
    full_name: str | None = None,
    redirect_url: str | None = None,
) -> LoginResponseModel:
    name = slugify(f"guest.{email}", separator=".")

    user = UserEntity(
        payload={
            "name": name,
            "attrib": {"email": email, "fullName": full_name},
            "data": {"isGuest": True},
        }
    )
    session = await Session.create(user, request=request)

    logger.debug(f"Guest user {email} logged in (redirect to {redirect_url})")
    return LoginResponseModel(
        detail=f"Guest user {email} logged in",
        token=session.token,
        user=session.user,
        redirect_url=redirect_url,
    )


async def handle_token_auth_callback(
    token: str,
    request: Request,
    current_user: UserEntity | None = None,
) -> LoginResponseModel:
    try:
        enc_data = await decrypt_json_urlsafe(token)
    except Exception:
        msg = "Unable to decrypt token"
        log_traceback()
        raise BadRequestException(msg)

    try:
        payload = TokenPayload(**enc_data.data)
    except Exception:
        raise BadRequestException("Invalid token payload format")

    if current_user and current_user.session:
        # user is already logged in. construct the response

        return LoginResponseModel(
            detail=f"User {current_user.name} already logged in",
            token=current_user.session.token,
            user=current_user.payload,
            redirect_url=payload.redirect_url,
        )

    if not await enc_data.validate_nonce():
        logger.debug(f"Token for guest user {payload.email} expired")
        await send_extend_email(payload, base_url=server_url_from_request(request))
        raise UnauthorizedException(
            "Your email link already expired or was used before. "
            "We're sending you a new one."
        )

    if payload.is_guest:
        if not payload.project_name:
            msg = "Guest user token must contain project name"
            raise BadRequestException(msg)
        exists = await GuestUsers.exists(
            payload.email, project_name=payload.project_name
        )
        if not exists:
            msg = (
                f"Guest user {payload.email} "
                f"does not exist in project {payload.project_name}"
            )
            raise UnauthorizedException(msg)

    else:
        # For future use. For now we only support guest users.
        msg = "Token is not for guest use"
        raise BadRequestException(msg)

    return await create_guest_user_session(
        email=payload.email,
        request=request,
        full_name=payload.full_name,
        redirect_url=payload.redirect_url,
    )

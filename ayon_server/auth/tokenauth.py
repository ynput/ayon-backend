from fastapi import Request

from ayon_server.auth.session import Session
from ayon_server.entities import UserEntity
from ayon_server.exceptions import (
    BadRequestException,
    InvalidSettingsException,
    UnauthorizedException,
)
from ayon_server.helpers.crypto import decrypt_json_urlsafe, encrypt_json_urlsafe
from ayon_server.helpers.email import is_mailing_enabled, send_mail
from ayon_server.helpers.external_users import ExternalUsers
from ayon_server.logging import log_traceback, logger
from ayon_server.types import OPModel
from ayon_server.utils import server_url_from_request, slugify

from .models import LoginResponseModel

LINK_RENEWAL_TEMPLATE = """
<p>
Hello {full_name},
</p>

<p>
the invite link you used to log in to Ayon has expired.
Please use the following link to log in again:
</p>

<p>
<a clicktracking=off href="{invite_link}">Login to ayon</a>
</p>
"""


class TokenPayload(OPModel):
    email: str
    external: bool = True
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
    external: bool = True,
    project_name: str | None = None,
    redirect_url: str | None = None,
) -> None:
    if not await is_mailing_enabled():
        raise InvalidSettingsException(
            "Mailing is not enabled. Please check the server settings."
        )

    payload = TokenPayload(
        email=email,
        full_name=full_name,
        external=external,
        project_name=project_name,
        redirect_url=redirect_url,
    )

    enc_data = await encrypt_json_urlsafe(payload.dict(exclude_none=True))
    token = enc_data.token
    await enc_data.set_nonce(ttl=3600 * 24)

    subject = subject or "Invitation to Ayon instance"
    body = body_template.format(
        full_name=full_name or "User",
        project_name=project_name or "the project",
        invite_link=f"{base_url}/login/_token?q={token}",
        redirect_url=redirect_url or "the ayon homepage",
    )

    await send_mail([email], subject, html=body)


async def send_extend_email(original_payload: TokenPayload, base_url: str) -> None:
    """Send an email to the user to extend their invite link.

    When a link is used for the first time to log in, it is invalidated.
    It still contain the original payload, so it "knows" where to take the user
    but in order to get the users session, user must get a new link.

    This is done automatically, when an expired link is used.
    """

    await send_invite_email(
        email=original_payload.email,
        base_url=base_url,
        body_template=LINK_RENEWAL_TEMPLATE,
        subject="Ayon access link renewal",
        full_name=original_payload.full_name,
        external=original_payload.external,
        project_name=original_payload.project_name,
        redirect_url=original_payload.redirect_url,
    )


async def create_external_user_session(
    email: str,
    request: Request,
    *,
    full_name: str | None = None,
    redirect_url: str | None = None,
) -> LoginResponseModel:
    name = slugify(f"external.{email}", separator=".")

    user = UserEntity(
        payload={
            "name": name,
            "attrib": {
                "email": email,
                "fullName": full_name,
            },
            "data": {
                "isExternal": True,
            },
        }
    )
    session = await Session.create(user, request=request)

    return LoginResponseModel(
        detail=f"External user {email} logged in",
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
        logger.debug(f"Token for external user {payload.email} expired")

        await send_extend_email(
            original_payload=payload,
            base_url=server_url_from_request(request),
        )

        raise UnauthorizedException(
            "Your email link already expired or was used before. "
            "We're sending you a new one."
        )

    if payload.external:
        if not payload.project_name:
            msg = "External user token must contain project name"
            raise BadRequestException(msg)
        exists = await ExternalUsers.exists(
            payload.email, project_name=payload.project_name
        )
        if not exists:
            msg = (
                f"External user {payload.email} "
                f"does not exist in project {payload.project_name}"
            )
            raise UnauthorizedException(msg)

    else:
        # For future use. For now we only support external users.
        msg = "Token is not for external use"
        raise BadRequestException(msg)

    return await create_external_user_session(
        email=payload.email,
        request=request,
        full_name=payload.full_name,
        redirect_url=payload.redirect_url,
    )

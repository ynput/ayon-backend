from typing import Any

from fastapi import Request

from ayon_server.auth.session import Session
from ayon_server.entities import UserEntity
from ayon_server.exceptions import BadRequestException, InvalidSettingsException
from ayon_server.helpers.crypto import decrypt_json_urlsafe, encrypt_json_urlsafe
from ayon_server.helpers.email import is_mailing_enabled, send_mail
from ayon_server.logging import log_traceback, logger
from ayon_server.utils import slugify

from .models import LoginResponseModel

LINK_RENEWAL_TEMPLATE = """
<p>
Hello {full_name},
</p>

<p>
the invite link you used to log in to Ayon has expired or was used before.
Please use the following link to log in again:
</p>

<p>
<a clicktracking=off href="{invite_link}">Accept Invitation</a>
</p>

Thank you

"""


async def send_invite_email(
    email: str,
    base_url: str,
    body_template: str,
    *,
    full_name: str | None = None,
    subject: str | None = None,
    external: bool = False,
    project_name: str | None = None,
    redirect_url: str | None = None,
) -> None:
    if not await is_mailing_enabled():
        raise InvalidSettingsException(
            "Mailing is not enabled. Please check the server settings."
        )

    payload: dict[str, Any] = {"email": email}
    if full_name:
        payload["fullName"] = full_name
    if external:
        payload["external"] = True
    if project_name:
        payload["projectName"] = project_name
    if redirect_url:
        payload["redirectUrl"] = redirect_url

    enc_data = await encrypt_json_urlsafe(payload)
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


async def create_external_user_session(
    email: str,
    *,
    full_name: str | None = None,
    redirect_url: str | None = None,
    request: Request | None = None,
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
    request: Request | None = None,
) -> LoginResponseModel:
    try:
        enc_data = await decrypt_json_urlsafe(token)
    except Exception:
        msg = "Unable to decrypt token"
        log_traceback()
        raise BadRequestException(msg)

    payload = enc_data.data
    email = payload.get("email")
    if not email:
        msg = "Token does not contain email"
        raise BadRequestException(msg)

    print(f"Token payload: {payload}")

    if not await enc_data.validate_nonce():
        logger.debug(
            f"Token for external user {email} expired or replay attack detected"
        )

        # TODO
        # If the token is expired or used before, we can send a new one

        raise BadRequestException(
            "Your email link already expired or was used before. "
            "We're sending you a new one."
        )

    if not payload.get("external"):
        msg = "Token is not for external use"
        raise BadRequestException(msg)

    return await create_external_user_session(
        email=payload["email"],
        full_name=payload.get("fullName"),
        redirect_url=payload.get("redirectUrl"),
        request=request,
    )

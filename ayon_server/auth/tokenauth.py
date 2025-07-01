from typing import Any

from ayon_server.exceptions import InvalidSettingsException
from ayon_server.helpers.crypto import encrypt_json_urlsafe
from ayon_server.helpers.email import is_mailing_enabled, send_mail

BODY_TEMPLATE = """
<h3>Hey {full_name}</h3>,

<p>
Someone has invited you to join the project "{project_name}" on Ayon.
To accept the invitation, please click the link below:
</p>

<p>
<a clicktracking=off href="{invite_link}">Accept Invitation</a>
</p>

Cheers
"""


async def send_invite_email(
    email: str,
    base_url: str,
    *,
    body_template: str = BODY_TEMPLATE,
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

    token = await encrypt_json_urlsafe(payload)

    subject = subject or "Invitation to join Ayon project"
    body = body_template.format(
        full_name=full_name or "User",
        project_name=project_name or "the project",
        invite_link=f"{base_url}/login/_token?q={token}",
    )

    await send_mail([email], subject, html=body)

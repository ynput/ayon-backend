import asyncio
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Union

import httpx
from nxtools import logging
from pydantic import BaseModel, Field

from ayon_server.config import ayonconfig
from ayon_server.exceptions import AyonException
from ayon_server.helpers.cloud import get_cloud_api_headers

if TYPE_CHECKING:
    from ayon_server.entities import UserEntity

EMAIL_NOT_CONFIGURED: bool = False


class EmailRecipient(BaseModel):
    email: str = Field(..., example="john.doe@example.com")
    name: str = Field(..., example="John Doe")


def build_body(
    text: str | None = None,
    html: str | None = None,
) -> MIMEMultipart | MIMEText:
    body: MIMEMultipart | MIMEText
    if html:
        body = MIMEMultipart("alternative")
        body.attach(MIMEText(html, "html"))
        if text:
            body.attach(MIMEText(text, "plain"))
        else:
            body.attach(
                MIMEText("No plain text version of the message is available", "plain")
            )
    else:
        assert text is not None, "No text or html version of the message is available"
        body = MIMEText(text, "plain")
    return body


def send_smtp_email(
    recipients: list[str],
    subject: str,
    text: str | None = None,
    html: str | None = None,
) -> None:

    assert ayonconfig.email_smtp_host is not None, "SMTP server is not configured"
    assert ayonconfig.email_smtp_port is not None, "SMTP server is not configured"
    user = ayonconfig.email_smtp_user
    password = ayonconfig.email_smtp_pass

    if user:
        assert password is not None, "SMTP server password is not configured"

    message = build_body(text, html)
    message["Subject"] = subject
    message["From"] = ayonconfig.email_from
    message["To"] = ", ".join(recipients)

    with smtplib.SMTP(ayonconfig.email_smtp_host, ayonconfig.email_smtp_port) as smtp:
        if ayonconfig.email_smtp_tls:
            context = ssl.create_default_context()
            smtp.starttls(context=context)

        if user and password:
            smtp.login(user, password)

        smtp.sendmail(ayonconfig.email_from, recipients, message.as_string())


async def send_api_email(
    recipients: list[str],
    subject: str,
    text: str | None = None,
    html: str | None = None,
) -> None:
    global EMAIL_NOT_CONFIGURED

    headers = await get_cloud_api_headers()

    payload = {
        "recipients": recipients,
        "subject": subject,
        "text": text,
        "html": html,
    }

    url = (f"{ayonconfig.ynput_cloud_api_url}/api/v1/sendmail",)
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 403:
            EMAIL_NOT_CONFIGURED = True
            raise AssertionError("No email subscription available")

        response.raise_for_status()


async def send_mail(
    recipients: list[Union[str, EmailRecipient, "UserEntity"]],
    subject: str,
    text: str | None = None,
    html: str | None = None,
) -> None:
    global EMAIL_NOT_CONFIGURED

    if EMAIL_NOT_CONFIGURED:
        raise AyonException("Email is not configured")

    recipient_list: list[str] = []
    for recipient in recipients:
        if isinstance(recipient, str):
            recipient_list.append(recipient)
        elif isinstance(recipient, EmailRecipient):
            recipient_list.append(f"{recipient.name} <{recipient.email}>")
        elif isinstance(recipient, UserEntity):
            recipient_list.append(
                f"{recipient.attrib.full_name or recipient.name } <{recipient.attrib.email}>"
            )

    # run send_smtp_email in a thread (we are in an async function)

    loop = asyncio.get_event_loop()
    try:
        with ThreadPoolExecutor() as executor:
            task = loop.run_in_executor(
                executor,
                send_smtp_email,
                recipient_list,
                subject,
                text,
                html,
            )
            await asyncio.gather(task)
    except AssertionError:
        pass
    except Exception:
        logging.traceback("Error while sending email")
        return
    else:
        return

    # if send_smtp_email fails, try send_api_email

    try:
        await send_api_email(recipient_list, subject, text, html)
    except AssertionError:
        EMAIL_NOT_CONFIGURED = True
        raise AyonException("Email is not configured")
    except Exception:
        raise AyonException("Error while sending email via API")

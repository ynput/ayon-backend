import asyncio
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Literal, Union

import httpx
from nxtools import log_traceback, logging
from pydantic import BaseModel, Field

from ayon_server.config import ayonconfig
from ayon_server.exceptions import AyonException
from ayon_server.helpers.cloud import get_cloud_api_headers

if TYPE_CHECKING:
    from ayon_server.entities import UserEntity

MailingEnabled = Literal[False, "smtp", "api"]
MAILING_ENABLED: MailingEnabled | None = None


async def is_mailing_enabled() -> MailingEnabled:
    """Check if mailing is enabled"""

    global MAILING_ENABLED

    if MAILING_ENABLED is not None:
        return MAILING_ENABLED

    if ayonconfig.email_smtp_host:
        MAILING_ENABLED = "smtp"
        logging.debug("Enabled SMTP email support")
        return MAILING_ENABLED

    try:
        headers = await get_cloud_api_headers()
    except AyonException:
        MAILING_ENABLED = False
        return MAILING_ENABLED

    try:
        async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
            res = await client.get(
                f"{ayonconfig.ynput_cloud_api_url}/api/v1/me",
                headers=headers,
            )
    except (httpx.ConnectError, httpx.TimeoutException):
        MAILING_ENABLED = False
        return MAILING_ENABLED

    try:
        res.raise_for_status()
    except httpx.HTTPStatusError:
        MAILING_ENABLED = False
        return MAILING_ENABLED

    data = res.json()
    if data.get("subscriptions"):
        MAILING_ENABLED = "api"
        logging.debug("Enabled Ynput Cloud API email support")
        return MAILING_ENABLED

    MAILING_ENABLED = False
    return MAILING_ENABLED


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
        if text:
            body.attach(MIMEText(text, "plain"))
        else:
            body.attach(
                MIMEText("No plain text version of the message is available", "plain")
            )
        body.attach(MIMEText(html, "html"))
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
    global MAILING_ENABLED

    headers = await get_cloud_api_headers()

    payload = {
        "recipients": recipients,
        "subject": subject,
        "text": text,
        "html": html,
    }

    url = f"{ayonconfig.ynput_cloud_api_url}/api/v1/sendmail"
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)

    try:
        response.raise_for_status()
    except Exception as e:
        log_traceback()
        MAILING_ENABLED = False
        raise AyonException("Error while sending email via API") from e


async def send_mail(
    recipients: list[Union[str, EmailRecipient, "UserEntity"]],
    subject: str,
    text: str | None = None,
    html: str | None = None,
) -> None:
    mailing_enabled = await is_mailing_enabled()
    if not mailing_enabled:
        raise AyonException("Email is not configured")

    recipient_list: list[str] = []
    for recipient in recipients:
        if isinstance(recipient, str):
            recipient_list.append(recipient)
        elif isinstance(recipient, EmailRecipient):
            recipient_list.append(f"{recipient.name} <{recipient.email}>")
        elif isinstance(recipient, UserEntity):
            full_name = recipient.attrib.full_name or recipient.name
            recipient_list.append(f"{full_name} <{recipient.attrib.email}>")

    # run send_smtp_email in a thread (we are in an async function)

    if mailing_enabled == "smtp":
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
            log_traceback("Error while sending email")
            return
        else:
            return

    elif mailing_enabled == "api":
        await send_api_email(recipient_list, subject, text, html)

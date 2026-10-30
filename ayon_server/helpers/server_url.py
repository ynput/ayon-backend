"""Public URL of the server for links sent to other people (emails).

Do not build such links from request headers (Referer, Host, X-Forwarded-*):
the client sets them, so anyone could get a link to their own site sent
from this server, e.g. a password reset link with a valid token.
"""

from urllib.parse import urlparse

from fastapi import Request

from ayon_server.config.serverconfig import get_server_config, update_server_config
from ayon_server.helpers.cloud import CloudUtils
from ayon_server.logging import logger


async def get_server_url() -> str | None:
    """Return the public URL of the server, or None if it is not known.

    Ynput Cloud knows the URL of the instances it manages. If it reports one,
    the server config is updated to match, so the settings show what is used.
    Otherwise the URL comes from the server config (see remember_server_url).
    """
    server_config = await get_server_config()
    stored_url = server_config.server_url.rstrip("/")
    cloud_info = await CloudUtils.get_cloud_info()
    if cloud_info.server_url:
        cloud_url = cloud_info.server_url.rstrip("/")
        if cloud_url != stored_url:
            await update_server_config({"server_url": cloud_url})
            logger.info(f"Server URL set to {cloud_url} (from Ynput Cloud)")
        return cloud_url
    return stored_url or None


async def remember_server_url(request: Request) -> None:
    """Store the URL an administrator opened the web interface from.

    Call only for requests of an administrator (a human, not a service):
    nobody else may decide where links sent by the server point to.
    Does nothing once the URL is set (or known to Ynput Cloud).
    """
    if await get_server_url():
        return
    if not (referer := request.headers.get("referer")):
        return  # not the web interface (e.g. a script using an API key)
    parsed = urlparse(referer)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return
    server_url = f"{parsed.scheme}://{parsed.netloc}"
    await update_server_config({"server_url": server_url})
    logger.info(f"Server URL set to {server_url}")

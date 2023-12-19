from typing import Any

import httpx

from ayon_server.config import ayonconfig
from ayon_server.exceptions import AyonException, ForbiddenException
from ayon_server.lib.postgres import Postgres

HEADERS: dict[str, str] = {}


async def get_headers() -> dict[str, str]:
    """Get the headers for the marketplace API"""

    if HEADERS:
        return HEADERS

    res = await Postgres.fetch("SELECT value FROM config WHERE key = 'instanceId'")
    if not res:
        raise AyonException("instance id not set. This shouldn't happen.")
    instance_id = res[0]["value"]

    res = await Postgres.fetch(
        "SELECT value FROM secrets WHERE name = 'ynput_cloud_key'"
    )
    if not res:
        raise ForbiddenException("Ayon is not connected to Ynput Cloud [ERR 1]")
    ynput_cloud_key = res[0]["value"]
    HEADERS.update(
        {
            "x-ynput-cloud-instance": instance_id,
            "x-ynput-cloud-key": ynput_cloud_key,
        }
    )
    return HEADERS


async def get_marketplace_data(
    *args: str,
) -> dict[str, Any]:
    """Get data from the marketplace API"""

    endpoint = "/".join(args)

    headers = await get_headers()

    if not headers:
        raise ForbiddenException("Ayon is not connected to Ynput Cloud [ERR 2]")

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        res = await client.get(
            f"{ayonconfig.ynput_cloud_api_url}/api/v1/marketplace/{endpoint}",
            headers=headers,
        )

    if res.status_code == 401:
        HEADERS.clear()
        raise ForbiddenException("Unauthorized instance")

    res.raise_for_status()  # should not happen

    return res.json()

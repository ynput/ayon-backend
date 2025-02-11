from typing import Any

import httpx
import semver

from ayon_server.addons.library import AddonLibrary
from ayon_server.config import ayonconfig
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    ServiceUnavailableException,
)
from ayon_server.helpers.cloud import CloudUtils
from ayon_server.lib.postgres import Postgres
from ayon_server.version import __version__ as ayon_version


async def get_market_data(
    *args: str,
    api_version: str = "v1",
) -> dict[str, Any]:
    """Get data from the market API"""

    endpoint = "/".join(args)

    try:
        headers = await CloudUtils.get_api_headers()
    except ForbiddenException:
        headers = {}

    headers["X-Ayon-Version"] = ayon_version

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        res = await client.get(
            f"{ayonconfig.ynput_cloud_api_url}/api/{api_version}/{endpoint}",
            headers=headers,
        )

    if res.status_code == 401:
        raise ForbiddenException("Unauthorized instance")

    if res.status_code >= 400 and res.status_code < 500:
        raise BadRequestException("Bad request to Market API")

    if res.status_code >= 500:
        raise ServiceUnavailableException("Market API error")

    return res.json()


async def get_local_latest_addon_versions() -> dict[str, str]:
    """Get the current latest versions of installed addons

    Used to check if there are new versions available
    """

    result = {}
    for addon_name, definition in AddonLibrary.items():
        if not definition.latest:
            continue
        result[addon_name] = definition.latest.version
    return result


async def get_local_production_addon_versions() -> dict[str, str]:
    """Get the current production versions of installed addons

    Used to check if there are new versions available
    """

    res = await Postgres.fetch(
        "SELECT data->'addons' as addons FROM bundles WHERE is_production"
    )
    if not res:
        return {}

    return res[0]["addons"] or {}


def is_compatible(requirement: str | None = None) -> bool:
    if requirement is None:
        return True
    conditions = requirement.split(",")
    for condition in conditions:
        condition = condition.strip()
        if not semver.match(ayon_version, condition):
            return False
    return True

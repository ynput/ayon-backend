import httpx

from ayon_server.config import ayonconfig
from ayon_server.exceptions import AyonException
from ayon_server.helpers.cloud import CloudUtils
from ayon_server.helpers.download_addon import download_addon
from ayon_server.helpers.get_downloaded_addons import get_downloaded_addons
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.version import __version__ as ayon_version
from maintenance.maintenance_task import StudioMaintenanceTask


async def get_download_url(addon_name: str, addon_version: str) -> str:
    if ayonconfig.offline_mode:
        raise AyonException("Cannot get download URL in offline mode")
    headers = await CloudUtils.get_api_headers()
    headers["X-Ayon-Version"] = ayon_version

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        endpoint = f"addons/{addon_name}/{addon_version}"
        res = await client.get(
            f"{ayonconfig.ynput_cloud_api_url}/api/v2/market/{endpoint}",
            headers=headers,
        )
        data = res.json()
        return data["url"]


async def download_addons() -> None:
    await Redis.delete("global", "required-addons")
    required_addons = await CloudUtils.get_required_addons()

    if not required_addons:
        return

    downloaded_addons = get_downloaded_addons()
    for addon_name, addon_version in required_addons:
        # Do we have the required addon downloaded?

        # Running as maintenance task. Ensure addon is downloaded,
        # and trigger "restart required" after downloading.
        if (addon_name, addon_version) not in downloaded_addons:
            try:
                url = await get_download_url(addon_name, addon_version)
            except Exception:
                logger.debug(
                    f"Failed to get download URL for {addon_name} {addon_version}"
                )
                continue

            await download_addon(
                addon_name=addon_name,
                addon_version=addon_version,
                url=url,
                no_queue=True,
            )
            logger.debug(f"Downloaded required addon {addon_name} {addon_version}")


class AutoUpdate(StudioMaintenanceTask):
    description = "Checking for updates"

    async def main(self):
        try:
            _ = await CloudUtils.get_api_headers()
        except Exception:
            # not connected to cloud. do nothing
            return

        await download_addons()

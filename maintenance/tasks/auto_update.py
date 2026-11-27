from ayon_server.helpers.cloud import CloudUtils
from ayon_server.helpers.download_addon import download_addon
from ayon_server.helpers.get_downloaded_addons import get_downloaded_addons
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from maintenance.maintenance_task import StudioMaintenanceTask


async def download_addons() -> None:
    res = await Postgres.fetchrow(
        "SELECT data->'addons' AS addons FROM public.bundles WHERE is_production"
    )
    addons = {k: v for k, v in ((res and res["addons"]) or {}).items() if v}

    try:
        # TODO: blacklist from config (not part of the POC)
        updates = await CloudUtils.get_addon_updates(addons, blacklist=[])
    except Exception as e:
        logger.debug(f"Failed to get addon updates: {e}")
        return

    # Startup applies these to the production bundle (lifespan.addon_update)
    await Redis.set_json(
        "global", "addon-updates", [[u["name"], u["version"]] for u in updates]
    )

    downloaded_addons = get_downloaded_addons()
    for update in updates:
        addon_name, addon_version = update["name"], update["version"]
        if (addon_name, addon_version) in downloaded_addons:
            continue
        try:
            # Installer triggers "restart required" after the download
            await download_addon(
                addon_name=addon_name,
                addon_version=addon_version,
                url=update["url"],
                no_queue=True,
            )
        except Exception as e:
            logger.warning(f"Failed to download {addon_name} {addon_version}: {e}")
            continue
        logger.debug(f"Downloaded addon update {addon_name} {addon_version}")


class AutoUpdate(StudioMaintenanceTask):
    description = "Checking for updates"

    async def main(self):
        try:
            _ = await CloudUtils.get_api_headers()
        except Exception:
            # not connected to cloud. do nothing
            return

        await download_addons()

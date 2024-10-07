import asyncio

from ayon_server.addons.library import AddonLibrary
from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.exceptions import NotFoundException
from ayon_server.helpers.get_downloaded_addons import get_downloaded_addons

FAKE_LIST = [{"name": "ynputcloud", "version": "1.0.9", "url": "myfakeurl"}]


async def install_addon(addon_name: str, addon_version: str, url: str) -> None:
    pass


async def run_auto_update() -> None:
    required_addons = FAKE_LIST

    downloaded_addons = get_downloaded_addons()
    for required_addon in required_addons:
        # Do we have the required addon downloaded?

        atuple = (required_addon["name"], required_addon["version"])
        if atuple not in downloaded_addons:
            await install_addon(
                addon_name=required_addon["name"],
                addon_version=required_addon["version"],
                url=required_addon["url"],
            )
            # Just download the addon. After restart, we'll be able to continue
            continue

        # Addon is downloaded. Check if it's active

        try:
            addon = AddonLibrary.addon(
                required_addon["name"], required_addon["version"]
            )
        except NotFoundException:
            # Addon is downloaded, but not active. Server restart is needed
            continue

        # Addon is active. Check if it's in the production bundle

        if not await addon.is_production():
            # Addon is active and in production we don't need to do anything
            continue

        # TODO: load the current production version of the addon

        # TODO: get the settings of the production version

        # TODO: migrate the settings to the new version

        # TODO: add the addon to the production bundle


class AutoUpdate(BackgroundWorker):
    """Auto-update server addons"""

    async def run(self):
        await asyncio.sleep(20)

        while True:
            await run_auto_update()
            await asyncio.sleep(3600)


auto_update = AutoUpdate()

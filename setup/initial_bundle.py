from typing import Any

from nxtools import logging

from ayon_server.events import EventStream
from ayon_server.installer.addons import install_addon_from_url
from ayon_server.lib.postgres import Postgres


async def create_initial_bundle(bundle_data: dict[str, Any]):
    """Download initial addons and create the first production bundle"""

    res = await Postgres.fetch("SELECT name FROM bundles LIMIT 1")
    if res:
        return

    addons = bundle_data.get("addons", [])
    bundle_addons = {}

    for addon_url in addons:
        logging.info(f"Installing addon from URL: {addon_url}")
        event_id = await EventStream.dispatch(
            "addons.install_from_url",
            description="Installing addon from URL",
            summary={"url": addon_url},
            finished=False,
        )

        zip_info = await install_addon_from_url(event_id, addon_url)
        bundle_addons[zip_info.name] = zip_info.version

    bundle_name = "InitialBundle"
    bundle_data = {"addons": bundle_addons}

    async with Postgres.acquire() as conn, conn.transaction():
        await Postgres.execute("UPDATE bundles SET is_production = FALSE")

        query = """
            INSERT INTO bundles (name, data, is_production)
            VALUES ($1, $2, TRUE)
            ON CONFLICT (name) DO UPDATE SET data = $2
        """

        await Postgres.execute(query, bundle_name, bundle_data)

from typing import Any

from nxtools import logging

from ayon_server.lib.postgres import Postgres


async def deploy_settings(settings: dict[str, Any], addons: dict[str, str]) -> None:
    logging.info("Deploying settings")
    await Postgres.execute("DELETE FROM public.settings")

    for addon_name in settings:
        for addon_version in settings[addon_name]:
            addon_settings = settings[addon_name][addon_version]

            logging.info(f"Saving settings for {addon_name} {addon_version}")

            await Postgres.execute(
                """
                INSERT INTO settings (addon_name, addon_version, data)
                VALUES ($1, $2, $3)
                """,
                addon_name,
                addon_version,
                addon_settings,
            )

    await Postgres.execute("DELETE FROM public.addon_versions")
    for addon_name, addon_version in addons.items():
        await Postgres.execute(
            """
            INSERT INTO public.addon_versions (name, production_version)
            VALUES ($1, $2)
            """,
            addon_name,
            addon_version,
        )

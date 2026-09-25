__all__ = ["AddonSettingsCache", "AddonKey", "SettingsCache"]

import time
from dataclasses import dataclass
from typing import Any

from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger


@dataclass
class AddonSettingsCache:
    studio: dict[str, Any] | None = None
    project: dict[str, Any] | None = None
    site: dict[str, Any] | None = None
    project_site: dict[str, Any] | None = None


AddonKey = tuple[str, str]
SettingsCache = dict[AddonKey, AddonSettingsCache]


async def load_all_settings(
    addons: dict[str, str],
    variant: str = "production",
    project_name: str | None = None,
    user_name: str | None = None,
    site_id: str | None = None,
) -> SettingsCache:
    if site_id and not user_name:
        raise BadRequestException("User name is required when site ID is provided")

    start_time = time.time()
    hashes = []
    for addon_name, addon_version in addons.items():
        hashes.append(f"{addon_name}-{addon_version}")

    result: SettingsCache = {}

    # Studio level settings

    query = """
        SELECT addon_name, addon_version, data
        FROM public.settings
        WHERE
            addon_name || '-' || addon_version = ANY($1)
        AND variant = $2
    """

    async for row in Postgres.iterate(query, hashes, variant):
        key = row["addon_name"], row["addon_version"]
        result[key] = AddonSettingsCache(studio=row["data"])

    if site_id and user_name:
        query = """
            SELECT addon_name, addon_version, data
            FROM public.site_settings
            WHERE
                addon_name || '-' || addon_version = ANY($1)
            AND site_id = $2
            AND user_name = $3
        """
        async for row in Postgres.iterate(query, hashes, site_id, user_name):
            key = row["addon_name"], row["addon_version"]
            if key not in result:
                result[key] = AddonSettingsCache()
            result[key].site = row["data"]

    # Project level settings

    if project_name:
        query = f"""
            SELECT addon_name, addon_version, data
            FROM project_{project_name}.settings
            WHERE
                addon_name || '-' || addon_version = ANY($1)
            AND variant = $2
        """

        async for row in Postgres.iterate(query, hashes, variant):
            key = row["addon_name"], row["addon_version"]
            if key not in result:
                result[key] = AddonSettingsCache()
            result[key].project = row["data"]

        # Project site level settings

        if site_id and user_name and project_name:
            query = f"""
                SELECT addon_name, addon_version, data
                FROM project_{project_name}.project_site_settings
                WHERE
                    addon_name || '-' || addon_version = ANY($1)
                AND site_id = $2
                AND user_name = $3
            """
            async for row in Postgres.iterate(query, hashes, site_id, user_name):
                key = row["addon_name"], row["addon_version"]
                if key not in result:
                    result[key] = AddonSettingsCache()
                result[key].project_site = row["data"]

    logger.trace(f"Settings cache loaded in {time.time() - start_time:.2f} seconds")

    return result

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
    if site_id and not project_name:
        raise BadRequestException("Project name is required when site ID is provided")

    start_time = time.time()
    hashes = []

    for addon_name, addon_version in addons.items():
        hashes.append(f"{addon_name}-{addon_version}")

    cols = [
        "st.addon_name",
        "st.addon_version",
        "st.data as studio",
    ]
    joins = []
    conds = [
        "st.addon_name || '-' || st.addon_version = ANY($1)",
        "st.variant = $2",
    ]
    vals: list[Any] = [hashes, variant]
    if project_name:
        cols.append("pr.data as project")
        joins.append(
            f"""
            LEFT JOIN project_{project_name}.settings as pr
            ON
                pr.addon_name = st.addon_name
            AND pr.addon_version = st.addon_version
            AND pr.variant = st.variant
            """
        )
    if site_id:
        cols.append("si.data as site")
        joins.append(
            f"""
            LEFT JOIN project_{project_name}.project_site_settings as si
            ON
                si.addon_name = st.addon_name
            AND si.addon_version = st.addon_version
            AND si.variant = st.variant
            """
        )
        conds.extend(["si.site_id = $3", "si.user_name = $4"])
        vals.extend([site_id, user_name])

    query = f"""
    SELECT
        {','.join(cols)}
    FROM
        settings st
        {' '.join(joins)}
    WHERE
        {' AND '.join(conds)}
    """

    result: SettingsCache = {}
    async for row in Postgres.iterate(query, *vals):
        key = row["addon_name"], row["addon_version"]
        result[key] = AddonSettingsCache(
            studio=row["studio"],
            project=row.get("project"),
            site=row.get("site"),
        )
    logger.trace(f"Settings cache loaded in {time.time() - start_time:.2f} seconds")

    return result

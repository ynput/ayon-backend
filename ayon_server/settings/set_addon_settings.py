from typing import Any

from nxtools import logging

from ayon_server.lib.postgres import Connection, Postgres


async def _set_addon_settings(
    addon_name: str,
    addon_version: str,
    data: dict[str, Any] | None,
    *,
    project_name: str | None,
    variant: str,
    conn: Connection,
) -> None:
    schema = "public" if project_name is None else f"project_{project_name}"

    if not data:
        query = f"""
            DELETE FROM {schema}.settings
            WHERE addon_name = $1 AND addon_version = $2 AND variant = $3
            RETURNING data AS original_data, NULL AS updated_data;
        """

    else:
        query = f"""
            INSERT INTO {schema}.settings (addon_name, addon_version, variant, data)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (addon_name, addon_version, variant)
            DO UPDATE SET data = $4
            RETURNING data AS original_data, EXCLUDED.data AS updated_data;
        """

    res = await conn.fetch(query, addon_name, addon_version, variant, data)
    if not res:
        logging.warning(
            f"Addon settings not found: {addon_name} {addon_version} {variant}"
        )

    original_data = res[0]["original_data"] if res else None
    updated_data = res[0]["updated_data"] if res else None

    logging.info(f"Original data: {original_data}")
    logging.info(f"Updated data: {updated_data}")


async def set_addon_settings(
    addon_name: str,
    addon_version: str,
    data: dict[str, Any] | None,
    *,
    project_name: str | None = None,
    variant: str = "production",
    conn: Connection | None = None,
) -> None:
    if conn is not None:
        return await _set_addon_settings(
            addon_name,
            addon_version,
            data,
            project_name=project_name,
            variant=variant,
            conn=conn,
        )

    async with Postgres.acquire() as c, c.transaction():
        return await _set_addon_settings(
            addon_name,
            addon_version,
            data,
            project_name=project_name,
            variant=variant,
            conn=c,
        )

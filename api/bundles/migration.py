__all__ = ["migrate_settings_by_bundle"]

from typing import Any

from nxtools import logging

from ayon_server.addons.addon import BaseServerAddon
from ayon_server.addons.library import AddonLibrary
from ayon_server.exceptions import NotFoundException
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Connection, Postgres

AddonVersionsDict = dict[str, str]


async def _get_bundles_addons(
    source_bundle: str,
    target_bundle: str,
    conn: Connection,
) -> tuple[AddonVersionsDict, AddonVersionsDict]:
    """Get addons for source and target bundles."""

    source_addons: AddonVersionsDict | None = None
    target_addons: AddonVersionsDict | None = None
    res = await conn.fetch(
        "SELECT name, data FROM bundles WHERE name = ANY($1)",
        [source_bundle, target_bundle],
    )
    for row in res:
        if row["name"] == source_bundle:
            source_addons = row["data"].get("addons", {})
        elif row["name"] == target_bundle:
            target_addons = row["data"].get("addons", {})

    if not source_addons:
        raise NotFoundException(f"Source bundle {source_bundle} not found")
    elif not target_addons:
        raise NotFoundException(f"Target bundle {target_bundle} not found")

    # remove addons that has no version
    source_addons = {k: v for k, v in source_addons.items() if v}
    target_addons = {k: v for k, v in target_addons.items() if v}

    if not source_addons:
        raise NotFoundException(f"Source bundle {source_bundle} has no addons")
    elif not target_addons:
        raise NotFoundException(f"Target bundle {target_bundle} has no addons")

    return source_addons, target_addons


async def _migrate_addon_settings(
    source_addon: BaseServerAddon,
    target_addon: BaseServerAddon,
    source_variant: str,
    target_variant: str,
    with_projects: bool,
    conn: Connection,
) -> None:
    """Migrate settings from source to target addon."""

    # Studio settings

    # Load studio settings from source addon converted to the target version model
    new_studio_overrides: dict[str, Any]
    new_studio_overrides = await source_addon.get_studio_overrides(
        variant=source_variant,
        as_version=target_addon.version,
    )

    if new_studio_overrides:
        await conn.execute(
            """
            INSERT INTO settings (addon_name, addon_version, variant, data)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (addon_name, addon_version, variant)
            DO UPDATE SET data = $4
            """,
            target_addon.name,
            target_addon.version,
            target_variant,
            new_studio_overrides,
        )
    else:
        await conn.execute(
            """
            DELETE FROM settings
            WHERE addon_name = $1 AND addon_version = $2 AND variant = $3
            """,
            target_addon.name,
            target_addon.version,
            target_variant,
        )

    if not with_projects:
        return

    # Project settings

    project_names = [project.name for project in await get_project_list()]

    for project_name in project_names:
        # Load project settings from source addon converted to the target version model
        new_project_overrides: dict[str, Any]
        new_project_overrides = await source_addon.get_project_overrides(
            project_name=project_name,
            variant=source_variant,
            as_version=target_addon.version,
        )

        if new_project_overrides:
            await conn.execute(
                f"""
                INSERT INTO project_{project_name}.settings
                (addon_name, addon_version, variant, data)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (addon_name, addon_version, variant)
                DO UPDATE SET data = $4
                """,
                target_addon.name,
                target_addon.version,
                target_variant,
                new_project_overrides,
            )
        else:
            await conn.execute(
                f"""
                DELETE FROM project_{project_name}.settings
                WHERE addon_name = $1 AND addon_version = $2 AND variant = $3
                """,
                target_addon.name,
                target_addon.version,
                target_variant,
            )

        # Project site settings

        site_info = await conn.fetch(
            f"""
            SELECT site_id, user_name, data
            FROM project_{project_name}.project_site_settings
            WHERE addon_name = $1 AND addon_version = $2
            """,
            source_addon.name,
            source_addon.version,
        )
        for row in site_info:
            if not row["data"]:
                continue
            site_id, user_name = row["site_id"], row["user_name"]

            # Load project site settings from source addon
            # converted to the target version model

            new_site_overrides: dict[str, Any]
            new_site_overrides = await source_addon.get_project_site_overrides(
                project_name=project_name,
                site_id=site_id,
                user_name=user_name,
                as_version=target_addon.version,
            )

            if new_site_overrides:
                await conn.execute(
                    f"""
                    INSERT INTO project_{project_name}.project_site_settings
                    (addon_name, addon_version, site_id, user_name, data)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (addon_name, addon_version, site_id, user_name)
                    DO UPDATE SET data = $5
                    """,
                    target_addon.name,
                    target_addon.version,
                    site_id,
                    user_name,
                    new_site_overrides,
                )
            else:
                await conn.execute(
                    f"""
                    DELETE FROM project_{project_name}.project_site_settings
                    WHERE addon_name = $1
                    AND addon_version = $2
                    AND site_id = $3
                    AND user_name = $4
                    """,
                    target_addon.name,
                    target_addon.version,
                    site_id,
                    user_name,
                )


async def _migrate_settings_by_bundle(
    source_bundle: str,
    target_bundle: str,
    source_variant: str,
    target_variant: str,
    with_projects: bool,
    conn: Connection,
) -> None:
    """
    Perform migration of settings from source to
    target bundle in a given transaction.
    """
    source_addons, target_addons = await _get_bundles_addons(
        source_bundle, target_bundle, conn
    )

    # get addons that are present in both source and target bundles
    # (i.e. addons that need to be migrated)
    addons_to_migrate = set(source_addons.keys()) & set(target_addons.keys())

    for addon_name in addons_to_migrate:
        source_version = source_addons[addon_name]
        target_version = target_addons[addon_name]

        # get addon instances

        try:
            source_addon = AddonLibrary.addon(addon_name, source_version)
        except NotFoundException:
            logging.warning(
                f"Source addon {addon_name} version {source_version} is not installed"
            )
            continue

        try:
            target_addon = AddonLibrary.addon(addon_name, target_version)
        except NotFoundException:
            logging.warning(
                f"Target addon {addon_name} version {target_version} is not installed"
            )
            continue

        # perform migration of addon settings

        await _migrate_addon_settings(
            source_addon,
            target_addon,
            source_variant,
            target_variant,
            with_projects,
            conn,
        )


#
# The main function that is called from the API
#


async def migrate_settings_by_bundle(
    source_bundle: str,
    target_bundle: str,
    source_variant: str,
    target_variant: str,
    with_projects: bool = True,
    conn: Connection | None = None,
) -> None:
    if conn:
        await _migrate_settings_by_bundle(
            source_bundle,
            target_bundle,
            source_variant,
            target_variant,
            with_projects,
            conn,
        )

    else:
        async with Postgres.acquire() as _conn, _conn.transaction():
            await _migrate_settings_by_bundle(
                source_bundle,
                target_bundle,
                source_variant,
                target_variant,
                with_projects,
                _conn,
            )

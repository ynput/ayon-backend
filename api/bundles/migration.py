__all__ = ["migrate_settings_by_bundle"]

from typing import Any

from nxtools import logging

from ayon_server.addons.addon import BaseServerAddon
from ayon_server.addons.library import AddonLibrary
from ayon_server.config import ayonconfig
from ayon_server.events import EventStream
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
) -> list[dict[str, Any]]:
    """Migrate settings from source to target addon.

    Returns a list of events that were created during migration.
    """

    # Studio settings

    # Load studio settings from source addon converted to the target version model
    new_studio_overrides: dict[str, Any]
    new_studio_overrides = await source_addon.get_studio_overrides(
        variant=source_variant,
        as_version=target_addon.version,
    )

    events: list[dict[str, Any]] = []
    event_head = f"{target_addon.name} {target_addon.version} {target_variant}"

    event_created = False
    event_payload = {}

    if new_studio_overrides:
        # fetch the original studio settings
        res = await conn.fetch(
            """
            SELECT data FROM settings
            WHERE addon_name = $1 AND addon_version = $2 AND variant = $3
            """,
            target_addon.name,
            target_addon.version,
            target_variant,
        )

        do_copy = False

        if res:
            original_data = res[0]["data"]
            if original_data != new_studio_overrides:
                do_copy = True
                if ayonconfig.audit_trail:
                    event_payload["originalValue"] = original_data
                    event_payload["newValue"] = new_studio_overrides
        else:
            do_copy = True
            if ayonconfig.audit_trail:
                event_payload["originalValue"] = {}
                event_payload["newValue"] = new_studio_overrides

        if do_copy:
            event_created = True
            event_description = "studio overrides changed during migration"

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
        res = await conn.fetch(
            """
            DELETE FROM settings
            WHERE addon_name = $1 AND addon_version = $2 AND variant = $3
            RETURNING data
            """,
            target_addon.name,
            target_addon.version,
            target_variant,
        )
        if res:
            event_created = True
            event_description = "studio overrides removed during migration"
            if ayonconfig.audit_trail:
                event_payload = {"originalValue": res[0]["data"], "newValue": {}}

    if event_created:
        events.append(
            {
                "description": f"{event_head} {event_description}",
                "summary": {
                    "addon_name": target_addon.name,
                    "addon_version": target_addon.version,
                    "variant": target_variant,
                },
                "payload": event_payload,
            }
        )

    if not with_projects:
        return events

    # Project settings

    project_names = [project.name for project in await get_project_list()]

    for project_name in project_names:
        event_created = False
        event_payload = {}

        # Load project settings from source addon converted to the target version model
        new_project_overrides: dict[str, Any]
        new_project_overrides = await source_addon.get_project_overrides(
            project_name=project_name,
            variant=source_variant,
            as_version=target_addon.version,
        )

        if new_project_overrides:
            # fetch the original project settings
            res = await conn.fetch(
                f"""
                SELECT data
                FROM project_{project_name}.settings
                WHERE addon_name = $1 AND addon_version = $2 AND variant = $3
                """,
                target_addon.name,
                target_addon.version,
                target_variant,
            )

            do_copy = False

            if res:
                original_data = res[0]["data"]
                if original_data != new_project_overrides:
                    do_copy = True
                    if ayonconfig.audit_trail:
                        event_payload["originalValue"] = original_data
                        event_payload["newValue"] = new_project_overrides
            else:
                do_copy = True
                if ayonconfig.audit_trail:
                    event_payload["originalValue"] = {}
                    event_payload["newValue"] = new_project_overrides

            if do_copy:
                event_created = True
                event_description = "project overrides changed during migration"

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
            res = await conn.fetch(
                f"""
                DELETE FROM project_{project_name}.settings
                WHERE addon_name = $1 AND addon_version = $2 AND variant = $3
                RETURNING data
                """,
                target_addon.name,
                target_addon.version,
                target_variant,
            )

            if res:
                event_created = True
                event_description = "project overrides removed during migration"
                if ayonconfig.audit_trail:
                    event_payload = {"originalValue": res[0]["data"], "newValue": {}}

        if event_created:
            events.append(
                {
                    "description": f"{event_head}: {event_description}",
                    "summary": {
                        "addon_name": target_addon.name,
                        "addon_version": target_addon.version,
                        "variant": target_variant,
                    },
                    "project": project_name,
                    "payload": event_payload,
                }
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

    return events


async def _migrate_settings_by_bundle(
    source_bundle: str,
    target_bundle: str,
    source_variant: str,
    target_variant: str,
    with_projects: bool,
    user_name: str | None,
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

        events = await _migrate_addon_settings(
            source_addon,
            target_addon,
            source_variant,
            target_variant,
            with_projects,
            conn,
        )

        for event in events:
            event["user"] = user_name
            await EventStream.dispatch("settings.changed", **event)


#
# The main function that is called from the API
#


async def migrate_settings_by_bundle(
    source_bundle: str,
    target_bundle: str,
    source_variant: str,
    target_variant: str,
    with_projects: bool = True,
    user_name: str | None = None,
    conn: Connection | None = None,
) -> None:
    if conn:
        await _migrate_settings_by_bundle(
            source_bundle,
            target_bundle,
            source_variant,
            target_variant,
            with_projects,
            user_name,
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
                user_name,
                _conn,
            )

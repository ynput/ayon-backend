from typing import TYPE_CHECKING, Any

from ayon_server.config import ayonconfig
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres

if TYPE_CHECKING:
    from ayon_server.addons.addon import BaseServerAddon


async def _migrate_addon_settings(
    source_addon: "BaseServerAddon",
    target_addon: "BaseServerAddon",
    source_variant: str,
    target_variant: str,
    with_projects: bool,
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
    event_description = ""

    event_created = False
    event_payload = {}

    if new_studio_overrides:
        # fetch the original studio settings
        res = await Postgres.fetch(
            """
            SELECT data FROM public.settings
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

            await Postgres.execute(
                """
                INSERT INTO public.settings (addon_name, addon_version, variant, data)
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
        res = await Postgres.fetch(
            """
            DELETE FROM public.settings
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
        summary = {
            "addon_name": target_addon.name,  # backwards compatibility
            "addon_version": target_addon.version,  # backwards compatibility
            "variant": target_variant,
            "source_version": source_addon.version,
            "source_variant": source_variant,
        }
        events.append(
            {
                "description": f"{event_head} {event_description}",
                "summary": summary,
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
            res = await Postgres.fetch(
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

                await Postgres.execute(
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
            res = await Postgres.fetch(
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
            summary = {
                "variant": target_variant,
                "source_version": source_addon.version,
                "source_variant": source_variant,
                "addon_name": target_addon.name,  # backwards compatibility
                "addon_version": target_addon.version,  # backwards compatibility
            }
            events.append(
                {
                    "description": f"{event_head}: {event_description}",
                    "summary": summary,
                    "project": project_name,
                    "payload": event_payload,
                }
            )

        # Project site settings

        site_info = await Postgres.fetch(
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
                await Postgres.execute(
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
                await Postgres.execute(
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


async def migrate_addon_settings(
    source_addon: "BaseServerAddon",
    target_addon: "BaseServerAddon",
    source_variant: str = "production",
    target_variant: str = "production",
    with_projects: bool = True,
) -> list[dict[str, Any]]:
    """Migrate settings from source to target addon.

    Returns a list of events that were created during migration.
    """

    async with Postgres.transaction():
        return await _migrate_addon_settings(
            source_addon,
            target_addon,
            source_variant,
            target_variant,
            with_projects,
        )

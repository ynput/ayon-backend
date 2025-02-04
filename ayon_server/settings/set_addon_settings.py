from typing import Any

from nxtools import logging

from ayon_server.addons import AddonLibrary
from ayon_server.config import ayonconfig
from ayon_server.events import EventStream
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.settings import BaseSettingsModel


async def set_addon_settings(
    addon_name: str,
    addon_version: str,
    data: dict[str, Any] | None,
    *,
    project_name: str | None = None,
    user_name: str | None = None,
    variant: str = "production",
) -> None:
    """Save addon settings to the database.

    This saves given addon settings to the database and triggers settings.changed event
    and calls Addon.on_settings_changed method.

    `data` must be a dictionary with overrides, not the full settings,
    otherwise all settings will be marked as overridden.

    If `project_name` is specified, the settings will be saved for the project,
    otherwise they will be saved for the studio.

    `user_name` is used only for the audit trail.
    """

    # Make sure we are not setting settings for a non-existent addon
    # This would raise NotFoundException if the addon does not exist

    addon = AddonLibrary.addon(addon_name, addon_version)
    model = addon.get_settings_model()
    if not model:
        msg = f"{addon_name} {addon_version} does not have settings"
        raise BadRequestException(msg)

    original_settings: BaseSettingsModel | None = None
    if project_name:
        original_settings = await addon.get_project_settings(
            project_name, variant=variant
        )
    else:
        original_settings = await addon.get_studio_settings(variant=variant)

    # Construct query

    schema = "public" if project_name is None else f"project_{project_name}"

    if not data:
        query = f"""
            DELETE FROM {schema}.settings
            WHERE addon_name = $1 AND addon_version = $2 AND variant = $3
            RETURNING data AS original_data, NULL AS updated_data;
        """
        args = ()

    else:
        query = f"""
            WITH existing AS (
                SELECT data AS original_data
                FROM {schema}.settings
                WHERE addon_name = $1 AND addon_version = $2 AND variant = $3
            )
            INSERT INTO {schema}.settings (addon_name, addon_version, variant, data)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (addon_name, addon_version, variant)
            DO UPDATE SET data = $4
            RETURNING
                (SELECT original_data FROM existing) AS original_data,
                settings.data AS updated_data;
        """
        args = (addon_name, addon_version, variant, data)

    res = await Postgres.fetch(query, *args)
    if not res:
        logging.warning(
            f"Addon settings not found: {addon_name} {addon_version} {variant}"
        )

    original_data = res[0]["original_data"] if res else None
    updated_data = res[0]["updated_data"] if res else None

    # Dispatch settings.changed event

    if ayonconfig.audit_trail:
        payload = {
            "originalValue": original_data,
            "newValue": updated_data,
        }

    otype = "project " if project_name else "studio "
    description = f"{addon_name} {addon_version} {variant} {otype}overrides changed"

    await EventStream.dispatch(
        topic="settings.changed",
        description=description,
        summary={
            "addon_name": addon_name,
            "addon_version": addon_version,
            "variant": variant,
        },
        user=user_name,
        project=project_name,
        payload=payload,
    )

    # Call Addon.on_settings_changed

    new_settings: BaseSettingsModel | None = None
    if project_name:
        new_settings = await addon.get_project_settings(
            project_name,
            variant=variant,
        )
    else:
        new_settings = await addon.get_studio_settings(variant=variant)

    if original_settings and new_settings:
        await addon.on_settings_changed(
            original_settings,
            new_settings,
            variant=variant,
            project_name=project_name,
        )

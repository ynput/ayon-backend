from addons.router import route_meta, router
from fastapi import Depends, Query, Response
from nxtools import logging

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import dep_current_user
from ayon_server.entities import UserEntity
from ayon_server.settings.common import postprocess_settings_schema


@router.get("/{addon_name}/{version}/siteSettings/schema", **route_meta)
async def get_addon_site_settings_schema(
    addon_name: str,
    version: str,
    # user: UserEntity = Depends(dep_current_user),
):
    """Return the JSON schema of the addon site settings."""

    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")

    model = addon.get_site_settings_model()

    if model is None:
        logging.error(f"No site settings schema for addon {addon_name}")
        return {}

    schema = model.schema()
    await postprocess_settings_schema(schema, model)
    schema["title"] = addon.friendly_name
    return schema


@router.get("/{addon_name}/{version}/siteSettings", **route_meta)
async def get_addon_site_settings(
    addon_name: str,
    version: str,
    site: str | None = Query(None),
    # user: UserEntity = Depends(dep_current_user),
):
    """Return the JSON schema of the addon site settings."""

    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")

    model = addon.get_site_settings_model()

    if model is None:
        logging.error(f"No site settings schema for addon {addon_name}")
        return {}

    ggg = model()
    return ggg  # :D

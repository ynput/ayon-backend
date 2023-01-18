from typing import Any

from addons.router import route_meta, router
from fastapi import Depends, Query, Response
from nxtools import logging

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import dep_current_user
from ayon_server.entities import UserEntity
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.settings.common import postprocess_settings_schema


@router.get("/{addon_name}/{version}/siteSettings/schema", **route_meta)
async def get_addon_site_settings_schema(
    addon_name: str,
    version: str,
    user: UserEntity = Depends(dep_current_user),
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


# TODO: consider adding an optional user_name query parameter to
# allow managers and admins to retrieve site_overrides of other users


@router.get("/{addon_name}/{version}/siteSettings", **route_meta)
async def get_addon_site_settings(
    addon_name: str,
    version: str,
    site: str = Query(...),
    user: UserEntity = Depends(dep_current_user),
):
    """Return the JSON schema of the addon site settings."""

    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")

    model = addon.get_site_settings_model()

    if model is None:
        logging.error(f"No site settings schema for addon {addon_name}")
        return {}

    data = {}
    query = """
        SELECT data FROM site_settings
        WHERE site_id = $1 AND addon_name = $2
        AND addon_version = $3 AND user_name = $4
    """
    async for row in Postgres.iterate(query, site, addon_name, version, user.name):
        data = row["data"]

    return model(**data)


@router.put("/{addon_name}/{version}/siteSettings", **route_meta)
async def set_addon_site_settings(
    payload: dict[str, Any],
    addon_name: str,
    version: str,
    site: str = Query(..., title="Site ID", regex="^[a-z0-9-]+$"),
    user: UserEntity = Depends(dep_current_user),
):

    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")

    model = addon.get_site_settings_model()

    if model is None:
        logging.error(f"No site settings schema for addon {addon_name}")
        return {}

    data = model(**payload)

    await Postgres.execute(
        """
        INSERT INTO site_settings (addon_name, addon_version, site_id, user_name, data)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (addon_name, addon_version, site_id, user_name)
        DO UPDATE SET data = $5
        """,
        addon_name,
        version,
        site,
        user.name,
        data.dict(),
    )

    return Response(status_code=204)

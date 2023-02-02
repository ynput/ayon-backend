from typing import Any

from addons.router import route_meta, router
from fastapi import Depends, Query, Response
from nxtools import logging
from pydantic.error_wrappers import ValidationError

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import dep_current_user
from ayon_server.entities import UserEntity
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.settings import (
    extract_overrides,
    list_overrides,
    postprocess_settings_schema,
)

from .common import ModifyOverridesRequestModel, pin_override, remove_override


@router.get("/{addon_name}/{addon_version}/schema", **route_meta)
async def get_addon_settings_schema(
    addon_name: str,
    addon_version: str,
    user: UserEntity = Depends(dep_current_user),
):
    """Return the JSON schema of the addon settings."""

    if (addon := AddonLibrary.addon(addon_name, addon_version)) is None:
        raise NotFoundException(f"Addon {addon_name} {addon_version} not found")

    model = addon.get_settings_model()

    if model is None:
        logging.error(f"No settings schema for addon {addon_name}")
        return {}

    schema = model.schema()
    await postprocess_settings_schema(schema, model)
    schema["title"] = addon.friendly_name
    return schema


@router.get("/{addon_name}/{addon_version}/settings", **route_meta)
async def get_addon_studio_settings(
    addon_name: str,
    addon_version: str,
    variant: str = Query("production"),
    user: UserEntity = Depends(dep_current_user),
):
    """Return the settings (including studio overrides) of the given addon."""

    if (addon := AddonLibrary.addon(addon_name, addon_version)) is None:
        raise NotFoundException(f"Addon {addon_name} {addon_version} not found")
    return await addon.get_studio_settings(variant=variant)


@router.post("/{addon_name}/{addon_version}/settings", **route_meta)
async def set_addon_studio_settings(
    payload: dict[str, Any],
    addon_name: str,
    addon_version: str,
    variant: str = Query("production"),
    user: UserEntity = Depends(dep_current_user),
):
    """Set the studio overrides for the given addon."""

    if not user.is_manager:
        raise ForbiddenException

    addon = AddonLibrary.addon(addon_name, addon_version)
    original = await addon.get_studio_settings(variant=variant)
    existing = await addon.get_studio_overrides(variant=variant)
    model = addon.get_settings_model()
    if (original is None) or (model is None):
        # This addon does not have settings
        return Response(status_code=400)
    try:
        data = extract_overrides(original, model(**payload), existing)
    except ValidationError:
        raise BadRequestException

    await Postgres.execute(
        """
        INSERT INTO settings
            (addon_name, addon_version, variant, data)
        VALUES
            ($1, $2, $3, $4)
        ON CONFLICT (addon_name, addon_version, variant)
            DO UPDATE SET data = $4
        """,
        addon_name,
        addon_version,
        variant,
        data,
    )
    return Response(status_code=204)


@router.get("/{addon_name}/{addon_version}/overrides", **route_meta)
async def get_addon_studio_overrides(
    addon_name: str,
    addon_version: str,
    variant: str = Query("production"),
    user: UserEntity = Depends(dep_current_user),
):
    if not user.is_manager:
        raise ForbiddenException

    addon = AddonLibrary.addon(addon_name, addon_version)
    settings = await addon.get_studio_settings(variant=variant)
    if settings is None:
        return {}
    overrides = await addon.get_studio_overrides(variant=variant)
    return list_overrides(settings, overrides)


@router.delete("/{addon_name}/{addon_version}/overrides", **route_meta)
async def delete_addon_studio_overrides(
    addon_name: str,
    addon_version: str,
    variant: str = Query("production"),
    user: UserEntity = Depends(dep_current_user),
):
    # TODO: Selectable snapshot

    if not user.is_manager:
        raise ForbiddenException

    # Ensure addon exists
    _ = AddonLibrary.addon(addon_name, addon_version)

    logging.info(f"Deleting {variant} studio settings of {addon_name} {addon_version}")
    await Postgres.execute(
        """
        DELETE FROM settings
        WHERE addon_name = $1
        AND addon_version = $2
        AND variant = $3
        """,
        addon_name,
        addon_version,
        variant,
    )
    return Response(status_code=204)


@router.post("/{addon_name}/{addon_version}/overrides", **route_meta)
async def modify_studio_overrides(
    payload: ModifyOverridesRequestModel,
    addon_name: str,
    addon_version: str,
    variant: str = Query("production"),
    user: UserEntity = Depends(dep_current_user),
):
    if not user.is_manager:
        raise ForbiddenException

    if payload.action == "delete":
        await remove_override(addon_name, addon_version, payload.path, variant=variant)
    elif payload.action == "pin":
        await pin_override(addon_name, addon_version, payload.path, variant=variant)
    return Response(status_code=204)

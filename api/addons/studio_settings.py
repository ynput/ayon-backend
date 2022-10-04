from typing import Any

from addons.router import router
from fastapi import Depends, Response
from nxtools import logging
from pydantic.error_wrappers import ValidationError

from openpype.addons import AddonLibrary
from openpype.api.dependencies import dep_current_user
from openpype.entities import UserEntity
from openpype.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from openpype.lib.postgres import Postgres
from openpype.settings import extract_overrides, list_overrides

from .common import ModifyOverridesRequestModel, pin_override, remove_override


@router.get(
    "/{addon_name}/{version}/settings",
  )
async def get_addon_studio_settings(
    addon_name: str,
    version: str,
    user: UserEntity = Depends(dep_current_user),
):
    """Return the settings (including studio overrides) of the given addon."""

    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")
    return await addon.get_studio_settings()


@router.post(
    "/{addon_name}/{version}/settings",
   )
async def set_addon_studio_settings(
    payload: dict[str, Any],
    addon_name: str,
    version: str,
    user: UserEntity = Depends(dep_current_user),
):
    """Set the studio overrides of the given addon."""

    if not user.is_manager:
        raise ForbiddenException

    addon = AddonLibrary.addon(addon_name, version)
    original = await addon.get_studio_settings()
    existing = await addon.get_studio_overrides()
    model = addon.get_settings_model()
    if (original is None) or (model is None):
        # This addon does not have settings
        return Response(status_code=400)
    try:
        data = extract_overrides(original, model(**payload), existing)
    except ValidationError:
        raise BadRequestException

    # Do not use versioning during the development (causes headaches)
    await Postgres.execute(
        "DELETE FROM settings WHERE addon_name = $1 AND addon_version = $2",
        addon_name,
        version,
    )

    await Postgres.execute(
        """
        INSERT INTO settings (addon_name, addon_version, data)
        VALUES ($1, $2, $3)
        """,
        addon_name,
        version,
        data,
    )
    return Response(status_code=204)


@router.get(
    "/{addon_name}/{version}/overrides",
  )
async def get_addon_studio_overrides(
    addon_name: str,
    version: str,
    user: UserEntity = Depends(dep_current_user),
):
    if not user.is_manager:
        raise ForbiddenException

    addon = AddonLibrary.addon(addon_name, version)
    settings = await addon.get_studio_settings()
    if settings is None:
        return {}
    overrides = await addon.get_studio_overrides()
    return list_overrides(settings, overrides)


@router.delete(
    "/{addon_name}/{version}/overrides",
   )
async def delete_addon_studio_overrides(
    addon_name: str,
    version: str,
    user: UserEntity = Depends(dep_current_user),
):
    if not user.is_manager:
        raise ForbiddenException

    # Ensure addon exists
    _ = AddonLibrary.addon(addon_name, version)

    logging.info(f"Deleting overrides for {addon_name} {version}")
    # we don't use versioned settings at the moment.
    # in the future, insert an empty dict instead
    await Postgres.execute(
        """
        DELETE FROM settings
        WHERE addon_name = $1
        AND addon_version = $2
        """,
        addon_name,
        version,
    )
    return Response(status_code=204)


@router.post(
    "/{addon_name}/{version}/overrides",
   )
async def modify_overrides(
    payload: ModifyOverridesRequestModel,
    addon_name: str,
    version: str,
    user: UserEntity = Depends(dep_current_user),
):
    if not user.is_manager:
        raise ForbiddenException

    if payload.action == "delete":
        await remove_override(addon_name, version, payload.path)
    elif payload.action == "pin":
        await pin_override(addon_name, version, payload.path)
    return Response(status_code=204)

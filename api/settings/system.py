import json
import os
from typing import Any

from fastapi import Response
from settings.router import router

from openpype.settings.system import SystemSettings, get_default_system_settings
from openpype.settings.utils import apply_overrides, extract_overrides, list_overrides

#
# Temporary utils, before we store overrides in the database
#


def _get_studio_overrides():
    try:
        with open("/tmp/studio.json") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _set_studio_overrides(overrides: dict[str, Any]):
    with open("/tmp/studio.json", "w") as f:
        json.dump(overrides, f)


def _delete_studio_overrides():
    try:
        os.remove("/tmp/studio.json")
    except FileNotFoundError:
        pass


#
# Endpoints
#


@router.get("/system/schema")
async def get_system_settings_schema():
    """Return a JSON schema for the system settings."""
    return SystemSettings.schema()


@router.get("/system")
async def get_system_settings() -> SystemSettings:
    """Return the system settings."""
    defaults = get_default_system_settings()
    overrides = _get_studio_overrides()
    return apply_overrides(defaults, overrides)


@router.put("/system", response_class=Response)
async def set_system_settings(overrides: SystemSettings):
    """Set the system settings."""
    defaults = get_default_system_settings()
    old_overrides = _get_studio_overrides()
    new_overrides = extract_overrides(defaults, overrides, old_overrides)
    _set_studio_overrides(new_overrides)
    return Response(status_code=204)


@router.delete("/system", response_class=Response)
async def delete_studio_overrides():
    """Delete the studio overrides for the system settings."""
    _delete_studio_overrides()
    return Response(status_code=204)


@router.get("/system/overrides")
async def get_studio_overrides():
    """Return the studio overrides.
    This is a helper endpoint for creating the settings form.
    """
    defaults = get_default_system_settings()
    overrides = _get_studio_overrides()
    return list_overrides(defaults, overrides)

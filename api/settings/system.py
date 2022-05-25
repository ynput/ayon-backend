import os
import json
from typing import Any
from fastapi import Response
from settings.router import router

from openpype.settings.common import BaseSettingsModel
from openpype.settings.system import SystemSettings, get_default_system_settings


@router.get("/schema")
async def get_system_settings_schema():
    """Return a JSON schema for the system settings."""
    return SystemSettings.schema()


@router.get("/schema/project")
async def get_project_settings_schema():
    """Return a JSON schema for the project settings."""
    return Response(status_code=501)


def get_studio_overrides():
    try:
        with open("/tmp/studio.json") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def set_studio_overrides(overrides: dict[str, Any]):
    with open("/tmp/studio.json", "w") as f:
        json.dump(overrides, f)


def delete_studio_overrides():
    try:
        os.remove("/tmp/studio.json")
    except FileNotFoundError:
        pass


def apply_studio_overrides(
    settings: SystemSettings,
    overrides: dict[str, Any],
    verbose: bool = False,
) -> dict[str, Any]:
    result = {}

    def crawl(obj: BaseSettingsModel, override, target):
        if verbose:
            target["__overrides__"] = {}
        for name, field in obj.__fields__.items():
            child = getattr(obj, name)
            if isinstance(child, BaseSettingsModel):
                if child._isGroup:
                    print(f"{name} is a group")
                    if verbose:
                        if name in override:
                            target["__overrides__"][name] = {
                                "type": "group",
                                "level": "studio",
                                "value": override[name],
                            }
                        else:
                            target["__overrides__"][name] = {
                                "type": "group",
                                "level": "default",
                                "value": child.dict()
                            }

                target[name] = {}
                crawl(child, override.get(name, {}), target[name])

            else:
                # Naive types
                if name in override:
                    target[name] = override[name]
                    if verbose:
                        target["__overrides__"][name] = {
                            "type": "leaf",
                            "level": "studio",
                            "value": override[name],
                        }
                else:
                    target[name] = child
                    if verbose:
                        target["__overrides__"][name] = {
                            "type": "leaf",
                            "level": "default",
                            "value": child,
                        }

    crawl(settings, overrides, result)
    return result


@router.get("/system")
async def get_system_settings(verbose: bool = False) -> SystemSettings:
    """Return the system settings."""
    defaults = get_default_system_settings()
    overrides = get_studio_overrides()
    print("Overrides", overrides)
    return apply_studio_overrides(defaults, overrides, verbose)


@router.patch("/system")
async def set_system_settings(settings: dict[str, Any]):
    """Set the system settings."""
    set_studio_overrides(settings)
    return {"status": "ok"}


@router.delete("/system")
async def delete_system_settings():
    """Delete the system settings."""
    delete_studio_overrides()
    return {"status": "ok"}

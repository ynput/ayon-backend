import json
import os
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
    result: dict[str, Any] = {}

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
                                "value": child.dict(),
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


def list_overrides(
    obj: BaseSettingsModel,
    override: dict[str, Any],
    root: str = "root",
) -> dict[str, Any]:
    result = {}

    for name, field in obj.__fields__.items():
        child = getattr(obj, name)
        path = f"{root}_{name}"

        if isinstance(child, BaseSettingsModel):
            if child._isGroup:
                r = {"path": path, "type": "group"}
                if name in override:
                    r["level"] = "studio"
                    r["value"] = override[name]
                else:
                    r["level"] = "default"
                    r["value"] = child.dict()

                result[path] = r
            result.update(list_overrides(child, override.get(name, {}), path))

        else:
            # Naive types
            if name in override:
                ovr_from = override[name]
                ovr_level = "studio"
            else:
                ovr_from = child
                ovr_level = "default"

            result[path] = {
                "value": ovr_from,
                "level": ovr_level,
            }

    return result


@router.get("/system")
async def get_system_settings(verbose: bool = False) -> dict[str, Any]:
    """Return the system settings."""
    defaults = get_default_system_settings()
    overrides = get_studio_overrides()
    return apply_studio_overrides(defaults, overrides, verbose)


@router.patch("/system", response_class=Response)
async def set_system_settings(settings: dict[str, Any]):
    """Set the system settings."""
    set_studio_overrides(settings)
    return Response(status_code=204)


@router.delete("/system", response_class=Response)
async def delete_system_settings():
    """Delete the system settings."""
    delete_studio_overrides()
    return Response(status_code=204)


@router.get("/system/overrides")
async def get_system_overrides():
    """Return the system overrides."""
    defaults = get_default_system_settings()
    overrides = get_studio_overrides()
    return list_overrides(defaults, overrides)

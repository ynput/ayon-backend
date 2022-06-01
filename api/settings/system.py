import json
import os
from typing import Any

from fastapi import Response
from settings.router import router

from openpype.settings.common import BaseSettingsModel
from openpype.settings.system import SystemSettings, get_default_system_settings

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
# Overrides
#


def apply_overrides(
    settings: SystemSettings,
    overrides: dict[str, Any],
) -> SystemSettings:
    result: dict[str, Any] = {}

    def crawl(obj: BaseSettingsModel, override, target):
        for name, field in obj.__fields__.items():
            child = getattr(obj, name)
            if isinstance(child, BaseSettingsModel):
                target[name] = {}
                crawl(child, override.get(name, {}), target[name])
            else:
                # Naive types
                if name in override:
                    target[name] = override[name]
                else:
                    target[name] = child

    crawl(settings, overrides, result)
    return SystemSettings(**result)


def list_overrides(
    obj: BaseSettingsModel,
    override: dict[str, Any],
    crumbs: list[str] = None,
) -> dict[str, Any]:
    result = {}

    if crumbs is None:
        crumbs = []
        root = "root"
    else:
        root = "root_" + "_".join(crumbs)

    for name, field in obj.__fields__.items():
        child = getattr(obj, name)
        path = f"{root}_{name}"
        chcrumbs = [*crumbs, name]

        if isinstance(child, BaseSettingsModel):
            result[path] = {
                "path": chcrumbs,
                "type": "group" if child._isGroup else "branch",
                "level": "studio" if name in override else "default",
            }
            result.update(list_overrides(child, override.get(name, {}), chcrumbs))

        elif type(child) is list:
            r = {"path": chcrumbs, "type": "list"}
            if name in override:
                r["level"] = "studio"
            else:
                r["level"] = "default"

            result[path] = r
            for i, item in enumerate(child):
                if isinstance(item, BaseSettingsModel):
                    ovr = override.get(name, None)
                    if ovr is None:
                        ovr = {}
                    else:
                        ovr = ovr[i]
                    result.update(list_overrides(item, ovr, [*chcrumbs, f"{i}"]))
                    try:
                        result.update(
                            list_overrides(
                                item, override.get(name, [])[i], [*chcrumbs, f"{i}"]
                            )
                        )
                    except IndexError:
                        pass
                else:
                    result[f"{path}_{i}"] = {
                        "path": [*chcrumbs, f"{i}"],
                        "level": "default",
                        "value": item,
                    }
                    # TODO: overrides!!!

        else:
            # Naive types
            if name in override:
                ovr_from = override[name]
                ovr_level = "studio"
            else:
                ovr_from = child
                ovr_level = "default"

            result[path] = {
                "path": chcrumbs,
                "value": ovr_from,
                "level": ovr_level,
            }

    return result


def extract_overrides(
    default: SystemSettings,
    overriden: SystemSettings,
    existing: dict[str, Any] = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    def crawl(obj, ovr, ex, target):
        for name, field in obj.__fields__.items():
            child = getattr(obj, name)
            if isinstance(child, BaseSettingsModel) and not child._isGroup:
                if child.dict() != ovr.dict()[name] or (name in ex):
                    target[name] = {}
                    crawl(child, getattr(ovr, name), ex.get(name, {}), target[name])
            else:
                if getattr(ovr, name) != getattr(obj, name) or (name in ex):
                    target[name] = ovr.dict()[name]

    crawl(default, overriden, existing or {}, result)
    return result


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
    print(json.dumps(new_overrides, indent=2))
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

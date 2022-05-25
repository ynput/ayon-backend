from typing import Any
from fastapi import Response
from settings.router import router

from openpype.types import camelize
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


STUDIO_OVERRIDES = {
    "general": {
        "artist_count": 5,
    },
    "modules": {
        "ftrack": {
            "server": "https://openpype.studio.com",
            "enabled": True,
        },
    },
}


def apply_studio_overrides(settings: SystemSettings, overrides: dict[str, Any]):
    result = {}

    def crawl(obj: BaseSettingsModel, override, target):
        target["__overrides__"] = {}
        for name, field in obj.__fields__.items():
            cname = camelize(name)
            child = getattr(obj, name)
            if isinstance(child, BaseSettingsModel):
                if child._is_group:
                    if name in override:
                        target["__overrides__"][cname] = {
                            "level": "studio",
                            "value": override[name],
                        }

                target[cname] = {}
                crawl(child, override.get(name, {}), target[cname])

            else:
                # Naive types
                if name in override:
                    target[cname] = override[name]
                    target["__overrides__"][cname] = {
                        "type": "leaf",
                        "level": "studio",
                        "value": override[name],
                    }
                else:
                    target[cname] = child
                    target["__overrides__"][cname] = {
                        "type": "leaf",
                        "level": "default",
                        "value": child,
                    }

    crawl(settings, overrides, result)
    return result


@router.get("/system")
async def get_system_settings() -> SystemSettings:
    """Return the system settings."""
    defaults = get_default_system_settings()
    return apply_studio_overrides(defaults, STUDIO_OVERRIDES)

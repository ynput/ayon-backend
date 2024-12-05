__all__ = [
    "configuration",
    "install",
    "site_settings",
    "studio_settings",
    "project_settings",
    "delete_addon",
    "list_addons",
    "router",
]

from . import (
    configuration,
    delete_addon,
    install,
    list_addons,
    project_settings,
    site_settings,
    studio_settings,
)
from .router import router

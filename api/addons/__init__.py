__all__ = ["router"]

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

_ = (
    configuration,
    delete_addon,
    install,
    list_addons,
    project_settings,
    site_settings,
    studio_settings,
)

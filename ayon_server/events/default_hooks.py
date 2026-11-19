__all__ = ["DEFAULT_HOOKS"]

from typing import TYPE_CHECKING

from ayon_server.lib.redis import Redis
from ayon_server.logging import logger

from .base import HandlerType

if TYPE_CHECKING:
    from .base import EventModel


async def clear_settings_cache(event: "EventModel"):
    logger.trace("Clearing all-settings cache")
    await Redis.delete_ns("all-settings")


async def clear_active_versions_cache(event: "EventModel"):
    """Forget the addon versions of the bundles on all server instances"""
    from ayon_server.addons.library import AddonLibrary

    AddonLibrary.clear_active_versions_cache()


async def reload_attributes(event: "EventModel"):
    """Reload the attribute library on all server instances"""
    from ayon_server.entities.core.attrib import attribute_library

    await attribute_library.reload()


DEFAULT_HOOKS: list[tuple[str, HandlerType, bool]] = [
    ("settings.changed", clear_settings_cache, False),
    ("bundle.created", clear_settings_cache, False),
    ("bundle.updated", clear_settings_cache, False),
    ("bundle.created", clear_active_versions_cache, True),
    ("bundle.updated", clear_active_versions_cache, True),
    ("bundle.status_changed", clear_active_versions_cache, True),
    ("server.attributes_updated", reload_attributes, True),
]

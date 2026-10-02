__all__ = ["DEFAULT_HOOKS"]

from typing import TYPE_CHECKING

import aiocache

from ayon_server.lib.redis import Redis
from ayon_server.logging import logger

from .base import HandlerType

if TYPE_CHECKING:
    from .base import EventModel


async def clear_settings_cache(event: "EventModel"):
    logger.trace("Clearing all-settings cache")
    await Redis.delete_ns("all-settings")


async def clear_attribute_info_cache(event: "EventModel"):
    """Clear the in-memory aiocache for the /info attributes response.

    Called on all nodes via global hook so each instance flushes its own
    local cache immediately when attributes are updated.
    """
    logger.trace("Clearing attribute info cache")
    await aiocache.caches.get("default").clear()


DEFAULT_HOOKS: list[tuple[str, HandlerType, bool]] = [
    ("settings.changed", clear_settings_cache, False),
    ("bundle.created", clear_settings_cache, False),
    ("bundle.updated", clear_settings_cache, False),
    ("server.attributes_updated", clear_attribute_info_cache, True),
]

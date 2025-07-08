__all__ = ["DEFAULT_HOOKS"]

from typing import TYPE_CHECKING

from ayon_server.lib.redis import Redis
from ayon_server.logging import logger

from .base import HandlerType

if TYPE_CHECKING:
    from .base import EventModel


async def on_settings_changed(event: "EventModel"):
    if event.topic == "settings.changed" or event.summary.get("isDev", False):
        # If the event is about settings change ,
        # or a dev bundle has changed (because it affects addon list)
        # we clear the cache for all settings.
        logger.trace("Clearing all-settings cache")
        await Redis.delete_ns("all-settings")


DEFAULT_HOOKS: list[tuple[str, HandlerType, bool]] = [
    ("settings.changed", on_settings_changed, False),
    ("bundle.created", on_settings_changed, False),
    ("bundle.updated", on_settings_changed, False),
]

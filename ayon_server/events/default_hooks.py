__all__ = ["DEFAULT_HOOKS"]

from typing import TYPE_CHECKING

from ayon_server.lib.redis import Redis
from ayon_server.logging import logger

from .base import HandlerType

if TYPE_CHECKING:
    from .base import EventModel


async def on_settings_changed(event: "EventModel"):
    _ = event
    logger.trace("Clearing all-settings cache")
    await Redis.delete_ns("all-settings")


DEFAULT_HOOKS: list[tuple[str, HandlerType, bool]] = [
    ("settings.changed", on_settings_changed, False),
]

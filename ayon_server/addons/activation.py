"""Track production bundle changes and notify addons.

Each replica keeps its own snapshot of the production addon versions
and calls `on_addon_activate` / `on_addon_deactivate` for the difference
whenever a bundle changes. Hooks therefore run on every replica and
must be idempotent.
"""

import asyncio
from typing import TYPE_CHECKING

from ayon_server.addons.library import AddonLibrary
from ayon_server.events import EventStream
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import log_traceback

if TYPE_CHECKING:
    from ayon_server.events.base import EventModel

_lock = asyncio.Lock()
_active: set[tuple[str, str]] = set()


async def _get_production_addons() -> set[tuple[str, str]]:
    row = await Postgres.fetchrow(
        "SELECT data->'addons' AS addons FROM public.bundles WHERE is_production"
    )
    if not (row and row["addons"]):
        return set()
    return {(name, version) for name, version in row["addons"].items() if version}


async def sync_addon_activation(event: "EventModel | None" = None) -> None:
    global _active
    _ = event

    async with _lock:
        production = await _get_production_addons()

        for hook, items in (
            ("on_addon_deactivate", _active - production),
            ("on_addon_activate", production - _active),
        ):
            for addon_name, addon_version in sorted(items):
                try:
                    addon = AddonLibrary.addon(addon_name, addon_version)
                except NotFoundException:
                    continue  # client-only, missing or broken addon
                try:
                    await getattr(addon, hook)()
                except Exception:
                    log_traceback(f"Error in {addon_name} {addon_version} {hook}")

        _active = production


async def init_addon_activation() -> None:
    """Activate production addons and start tracking bundle changes.

    Must be called after all addons are set up.
    """
    for topic in ("bundle.created", "bundle.updated"):
        EventStream.subscribe(topic, sync_addon_activation, all_nodes=True)
    await sync_addon_activation()

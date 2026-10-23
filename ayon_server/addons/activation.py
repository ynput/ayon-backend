"""Track production/staging bundle changes and notify addons.

Each replica keeps its own snapshot of the variants (production, staging)
each addon version is used in, and calls `on_bundle_status_change`
for the addon versions whose variants changed whenever a bundle changes.
Hooks therefore run on every replica and must be idempotent.
Failed hooks are retried on the next bundle change.
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

AddonKey = tuple[str, str]

VARIANTS = ("production", "staging")

_lock = asyncio.Lock()

# Variants each addon version was last notified with.
# Addon versions without variants are omitted. None means the state
# is unknown (not notified yet or the hook failed), so the hook is called
# on the next sync regardless of the variants.
_state: dict[AddonKey, list[str] | None] = {}


async def _get_addon_variants() -> dict[AddonKey, list[str]]:
    result: dict[AddonKey, list[str]] = {}
    query = """
        SELECT is_production, is_staging, data->'addons' AS addons
        FROM public.bundles
        WHERE is_production OR is_staging
    """
    addons_by_variant: dict[str, dict[str, str | None]] = {}
    async for row in Postgres.iterate(query):
        for variant in VARIANTS:
            if row[f"is_{variant}"]:
                addons_by_variant[variant] = row["addons"] or {}

    for variant in VARIANTS:
        for name, version in addons_by_variant.get(variant, {}).items():
            if version:
                result.setdefault((name, version), []).append(variant)
    return result


async def sync_addon_activation(event: "EventModel | None" = None) -> None:
    global _state
    _ = event

    async with _lock:
        current = await _get_addon_variants()
        new_state: dict[AddonKey, list[str] | None] = {}

        for key in sorted(set(current) | set(_state)):
            addon_name, addon_version = key
            variants = current.get(key, [])
            previous = _state.get(key, [])
            if previous == variants:
                if variants:
                    new_state[key] = variants
                continue

            try:
                addon = AddonLibrary.addon(addon_name, addon_version)
            except NotFoundException:
                continue  # client-only, missing or broken addon

            try:
                await addon.on_bundle_status_change(variants)
            except Exception:
                log_traceback(
                    f"Error in {addon_name} {addon_version} on_bundle_status_change"
                )
                # Retry on the next bundle change
                new_state[key] = None
                continue

            if variants:
                new_state[key] = variants

        _state = new_state


async def init_addon_activation() -> None:
    """Notify all addons about their variants and start tracking bundle changes.

    Must be called after all addons are set up.
    """
    global _state

    # Call the hook for every loaded addon version on startup,
    # including those that are not used in any bundle
    _state = {
        (addon_name, addon_version): None
        for addon_name, definition in AddonLibrary.items()
        for addon_version in definition.versions
    }

    for topic in ("bundle.created", "bundle.updated", "bundle.deleted"):
        EventStream.subscribe(topic, sync_addon_activation, all_nodes=True)
    await sync_addon_activation()

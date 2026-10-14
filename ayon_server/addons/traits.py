"""Trait definitions provided by addons.

Addons describe the traits they define (client side, as Python dataclasses)
in a generated manifest shipped with the server part of the addon
(`server/traits.json`). This module loads those manifests and merges them
across all installed addon versions, so the frontend can render
representation traits.
"""

import os
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from ayon_server.addons.models import TraitDefinition, TraitDefinitionListItem
from ayon_server.lib.redis import Redis
from ayon_server.logging import log_traceback, logger
from ayon_server.utils import hash_data, json_loads

if TYPE_CHECKING:
    from ayon_server.events.base import EventModel

TRAITS_MANIFEST_FILENAME = "traits.json"
TRAITS_CACHE_NS = "trait-definitions"
SUPPORTED_MANIFEST_VERSIONS = {1}

TRAIT_VERSION_REGEX = re.compile(r"\.v(\d+)$")


class TraitConflict:
    """Same versioned trait ID defined with different data models."""

    def __init__(self, trait_id: str, sources: list[tuple[str, str, str]]):
        self.trait_id = trait_id
        # list of (addon_name, addon_version, schema_hash)
        self.sources = sources

    def summary(self) -> dict[str, Any]:
        return {
            "traitId": self.trait_id,
            "sources": [
                {"addonName": name, "addonVersion": version, "schemaHash": hsh}
                for name, version, hsh in self.sources
            ],
        }


def parse_trait_manifest(data: dict[str, Any]) -> list[TraitDefinition]:
    """Parse the content of a trait manifest file.

    Invalid trait entries are skipped (and logged), so one broken
    trait does not hide the rest of the manifest.
    """

    manifest_version = data.get("manifestVersion")
    if manifest_version not in SUPPORTED_MANIFEST_VERSIONS:
        raise ValueError(f"Unsupported trait manifest version: {manifest_version}")

    traits = data.get("traits") or {}
    if not isinstance(traits, dict):
        raise ValueError("Trait manifest 'traits' must be an object")

    result: list[TraitDefinition] = []
    for trait_id, entry in traits.items():
        try:
            definition = dict(entry.get("definition") or {})
            # The key of the manifest entry is authoritative
            definition["id"] = trait_id
            definition.setdefault(
                "versionlessId", TRAIT_VERSION_REGEX.sub("", trait_id)
            )
            if "version" not in definition:
                match = TRAIT_VERSION_REGEX.search(trait_id)
                definition["version"] = int(match[1]) if match else None
            definition.setdefault("name", trait_id)
            for key in ("hashes", "introducedIn", "deprecated"):
                if key in entry:
                    definition[key] = entry[key]
            result.append(TraitDefinition(**definition))
        except Exception as e:
            logger.warning(f"Invalid trait definition {trait_id}: {e}")
    return result


def load_trait_manifest(path: str) -> list[TraitDefinition]:
    """Load trait definitions from a manifest file.

    Returns an empty list if the file does not exist or cannot be parsed.
    """

    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json_loads(f.read())
        return parse_trait_manifest(data)
    except Exception:
        log_traceback(f"Unable to load trait manifest {path}")
        return []


def get_schema_hash(definition: TraitDefinition) -> str:
    """Return the data model hash of the definition.

    Prefer the hash stored in the manifest, fall back to hashing the schema.
    """
    if definition.hashes.schema_hash:
        return definition.hashes.schema_hash
    return f"sha256:{hash_data(definition.trait_schema)}"


def merge_trait_definitions(
    sources: Iterable[tuple[str, str, list[TraitDefinition]]],
) -> tuple[list[TraitDefinitionListItem], list[TraitConflict]]:
    """Merge trait definitions from multiple addon versions.

    `sources` is an iterable of (addon_name, addon_version, definitions),
    ordered from the oldest to the newest version of each addon.

    Definitions with the same versioned ID are merged into one item
    which lists all addon versions providing it. The definition from
    the last source wins, so description and UI hints come from the
    newest addon version. If the data model differs between sources,
    the item is flagged as a conflict.
    """

    items: dict[str, TraitDefinitionListItem] = {}
    schema_hashes: dict[str, list[tuple[str, str, str]]] = {}

    for addon_name, addon_version, definitions in sources:
        for definition in definitions:
            schema_hash = get_schema_hash(definition)
            seen = schema_hashes.setdefault(definition.id, [])
            seen.append((addon_name, addon_version, schema_hash))

            existing = items.get(definition.id)
            addon_versions = []
            conflict = False
            if existing is not None:
                conflict = existing.conflict or any(
                    hsh != schema_hash for _, _, hsh in seen
                )
                if existing.addon_name == addon_name:
                    addon_versions = existing.addon_versions
                else:
                    # A different addon defines the same trait ID
                    conflict = True

            items[definition.id] = TraitDefinitionListItem(
                **definition.dict(),
                addon_name=addon_name,
                addon_versions=[*addon_versions, addon_version],
                conflict=conflict,
            )

    conflicts = [
        TraitConflict(trait_id, schema_hashes[trait_id])
        for trait_id, item in items.items()
        if item.conflict
    ]
    return list(items.values()), conflicts


async def _collect_sources(
    variant: str | None,
) -> list[tuple[str, str, list[TraitDefinition]]]:
    from ayon_server.addons.library import AddonLibrary

    sources: list[tuple[str, str, list[TraitDefinition]]] = []

    if variant:
        library = AddonLibrary.getinstance()
        addons = await library.get_addons_by_variant(variant)
        candidates = [addon for addon in addons.values() if addon]
    else:
        # Versions are sorted from the oldest to the newest
        candidates = [
            addon
            for _, definition in AddonLibrary.items()
            for addon in definition.versions.values()
        ]

    for addon in candidates:
        try:
            definitions = await addon.get_trait_definitions()
        except Exception:
            log_traceback(f"Unable to get trait definitions of {addon}")
            continue
        if definitions:
            sources.append((addon.name, addon.version, definitions))
    return sources


async def _report_conflicts(conflicts: list[TraitConflict]) -> None:
    from ayon_server.events import EventStream

    for conflict in conflicts:
        summary = conflict.summary()
        sources = ", ".join(
            f"{name} {version}" for name, version, _ in conflict.sources
        )
        logger.warning(
            f"Trait {conflict.trait_id} is defined with different "
            f"data models in: {sources}"
        )
        try:
            await EventStream.dispatch(
                "traits.conflict",
                # Reuse the event for the same conflict instead of creating
                # a new one every time the cache is rebuilt
                hash=hash_data(["traits.conflict", summary]),
                reuse=True,
                description=(
                    f"Trait {conflict.trait_id} is defined with different data models"
                ),
                summary=summary,
            )
        except Exception:
            log_traceback("Unable to dispatch traits.conflict event")


async def get_trait_definitions(
    variant: str | None = None,
) -> list[TraitDefinitionListItem]:
    """Return trait definitions merged across installed addons.

    Without `variant`, all installed versions of all addons are used,
    so definitions of old trait versions stay available. With `variant`
    (production, staging or a dev bundle name), only addons of that
    bundle are used.

    The result is cached until the next `bundle.updated` event.
    """

    cache_key = variant or "_all"
    cached = await Redis.get_json(TRAITS_CACHE_NS, cache_key)
    if cached is not None:
        return [TraitDefinitionListItem(**item) for item in cached]

    sources = await _collect_sources(variant)
    items, conflicts = merge_trait_definitions(sources)
    if conflicts:
        await _report_conflicts(conflicts)

    await Redis.set_json(
        TRAITS_CACHE_NS,
        cache_key,
        [item.dict(by_alias=True) for item in items],
    )
    return items


async def clear_trait_definitions_cache(event: "EventModel | None" = None) -> None:
    """Clear cached trait definitions.

    Used as a `bundle.updated` event handler, therefore the optional
    event argument.
    """
    _ = event
    await Redis.delete_ns(TRAITS_CACHE_NS)

__all__ = ["migrate_settings"]

import asyncio
from typing import Any

from ayon_server.addons.library import AddonLibrary
from ayon_server.entities import UserEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.helpers.migrate_addon_settings import migrate_addon_settings
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger

AddonVersionsDict = dict[str, str]


async def _get_bundles_addons(
    source_bundle: str,
    target_bundle: str,
) -> tuple[AddonVersionsDict, AddonVersionsDict]:
    """Get addons for source and target bundles."""

    source_addons: AddonVersionsDict | None = None
    target_addons: AddonVersionsDict | None = None
    res = await Postgres.fetch(
        "SELECT name, data FROM public.bundles WHERE name = ANY($1)",
        [source_bundle, target_bundle],
    )
    for row in res:
        if row["name"] == source_bundle:
            source_addons = row["data"].get("addons", {})
        if row["name"] == target_bundle:
            target_addons = row["data"].get("addons", {})

    if not source_addons:
        raise NotFoundException(f"Source bundle {source_bundle} not found")
    elif not target_addons:
        raise NotFoundException(f"Target bundle {target_bundle} not found")

    # remove addons that has no version
    source_addons = {k: v for k, v in source_addons.items() if v}
    target_addons = {k: v for k, v in target_addons.items() if v}

    if not source_addons:
        raise NotFoundException(f"Source bundle {source_bundle} has no addons")
    elif not target_addons:
        raise NotFoundException(f"Target bundle {target_bundle} has no addons")

    return source_addons, target_addons


async def _dispatch_events(events: list[dict[str, Any]], user_name: str | None) -> None:
    for event in events:
        event["user"] = user_name
        await EventStream.dispatch("settings.changed", **event)


async def migrate_settings(
    source_bundle: str,
    target_bundle: str,
    source_variant: str,
    target_variant: str,
    with_projects: bool,
    user_name: str | None,
) -> None:
    """
    Perform migration of settings from source to
    target bundle in a given transaction.
    """

    events: list[dict[str, Any]] = []

    async with Postgres.transaction():
        if source_variant not in ("production", "staging"):
            if source_bundle != source_variant:
                raise BadRequestException(
                    "When source_variant is not production or staging, "
                    "source_bundle must be the same as source_variant"
                )

        if target_variant not in ("production", "staging"):
            if target_bundle != target_variant:
                raise BadRequestException(
                    "When target_variant is not production or staging, "
                    "target_bundle must be the same as target_variant"
                )

        source_addons, target_addons = await _get_bundles_addons(
            source_bundle, target_bundle
        )

        # get addons that are present in both source and target bundles
        # (i.e. addons that need to be migrated)
        addons_to_migrate = set(source_addons.keys()) & set(target_addons.keys())

        logger.debug(
            f"Migrating settings from {source_bundle} ({source_variant}) "
            f"to {target_bundle} ({target_variant})"
        )

        for addon_name in addons_to_migrate:
            source_version = source_addons[addon_name]
            target_version = target_addons[addon_name]

            # get addon instances

            try:
                source_addon = AddonLibrary.addon(addon_name, source_version)
            except NotFoundException:
                logger.warning(
                    f"Source addon {addon_name} {source_version} is not installed"
                )
                continue

            try:
                target_addon = AddonLibrary.addon(addon_name, target_version)
            except NotFoundException:
                logger.warning(
                    f"Target addon {addon_name} {target_version} is not installed"
                )
                continue

            # perform migration of addon settings

            events = await migrate_addon_settings(
                source_addon,
                target_addon,
                source_variant,
                target_variant,
                with_projects,
            )

    if events:
        asyncio.create_task(_dispatch_events(events, user_name))


async def migrate_server_addon_settings(
    addon_name: str,
    source_version: str,
    target_version: str,
    *,
    user: UserEntity | None = None,
) -> None:
    try:
        source_addon = AddonLibrary.addon(addon_name, source_version)
        target_addon = AddonLibrary.addon(addon_name, target_version)
    except NotFoundException as e:
        logger.warning(f"Unable to migrate server addon settings: {e}")
        return

    logger.info(
        f"Migrating server addon settings for {addon_name} "
        f"from {source_version} to {target_version}"
    )

    events = await migrate_addon_settings(
        source_addon,
        target_addon,
        source_variant="production",
        target_variant="production",
        with_projects=True,
    )
    if events:
        user_name = user.name if user else None
        asyncio.create_task(_dispatch_events(events, user_name))

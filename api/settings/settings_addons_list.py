__all__ = ["get_addon_list_for_settings", "AddonListForSettings"]

from typing import TypedDict

from ayon_server.addons import AddonLibrary
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger


class AddonListForSettings(TypedDict):
    addons: dict[str, str]
    inherited_addons: list[str]
    bundle_name: str
    project_name: str | None
    is_project_bundle: bool


async def get_addon_list_for_settings(
    bundle_name: str | None = None,
    project_name: str | None = None,
    project_bundle_name: str | None = None,
    variant: str = "production",
) -> AddonListForSettings:
    #
    # Get the studio bundle first
    #

    if (
        not project_bundle_name
        and bundle_name
        and bundle_name.startswith("__project__")
    ):
        project_bundle_name = bundle_name
        bundle_name = None

    if variant not in ("production", "staging"):
        # Dev bundle
        query = [
            """
            SELECT name, is_production, is_staging, data->'addons' as addons
            FROM bundles WHERE name = $1
            """,
            variant,
        ]
    elif bundle_name is None:
        # Current production / staging
        query = [
            f"""
            SELECT name, is_production, is_staging, data->'addons' as addons
            FROM bundles WHERE is_{variant} IS TRUE
            """
        ]
    else:
        # Explicit bundle name
        query = [
            """
            SELECT name, is_production, is_staging, data->'addons' as addons
            FROM bundles WHERE name = $1
            """,
            bundle_name,
        ]

    brow = await Postgres.fetch(*query)
    if not brow:
        raise NotFoundException(status_code=404, detail="Bundle not found")

    # Studio bundle name and list of addons from the studio bundle

    studio_bundle_name = brow[0]["name"]
    addons: dict[str, str] = {}

    for addon_name, addon_version in brow[0]["addons"].items():
        if addon_version is None:
            continue
        addons[addon_name] = addon_version
    logger.trace(f"Got studio bundle {studio_bundle_name}")

    #
    # Project bundle
    #

    # If project name is given, but no project bundle name,
    # get the project bundle name from the project data

    if (
        project_name
        and (not project_bundle_name)
        and variant in ("production", "staging")
    ):
        r = await Postgres.fetchrow(
            "SELECT data->'bundle' as bundle FROM projects WHERE name = $1",
            project_name,
        )
        if not r:
            raise NotFoundException(status_code=404, detail="Project not found")
        try:
            project_bundle_name = r["bundle"][variant]
            logger.trace(f"Got project bundle {project_bundle_name}")
        except Exception:
            project_bundle_name = None

    # If we know the project bundle name,
    # load the project bundle and merge it with the studio bundle

    if project_bundle_name:
        r = await Postgres.fetchrow(
            """
            SELECT
                b.data->'addons' as addons,
                p.name as project_name
            FROM bundles b
            JOIN projects p
                ON b.name = p.data->'bundle'->>$2
            WHERE
                b.name = $1
            AND coalesce((b.data->'is_project')::boolean, false)
            """,
            project_bundle_name,
            variant,
        )
        if not r:
            raise NotFoundException(
                status_code=404,
                detail=f"Project bundle {project_bundle_name} not found"
                f"Studio {variant} bundle is not set",
            )

        # In the case project name was not provided,
        # use resolved project name from the query
        project_name = r["project_name"]

        project_addons = r["addons"]
        inherited_addons: set[str] = set(addons.keys())

        for addon_name, addon_version in project_addons.items():
            if addon_version == "__inherit__":
                continue

            if addon_version is None:
                # addon explicitly disabled in the project bundle,
                # remove it from the list if present
                if addon_name in addons:
                    logger.trace(f"Disabling addon {addon_name} via project bundle")
                    del addons[addon_name]
                    inherited_addons.discard(addon_name)
                continue

            try:
                addon = AddonLibrary.addon(addon_name, addon_version)
            except NotFoundException:
                # addon not found, we use whatever is set in the
                # studio bundle
                continue

            if not addon.project_can_override_addon_version:
                # addon version cannot be overridden by the project bundle
                continue

            logger.debug(f"Overriding addon {addon_name} to version {addon_version}")
            addons[addon_name] = addon_version
            inherited_addons.discard(addon_name)

    assert studio_bundle_name is not None, (
        "Bundle name is None"
    )  # won't happen, keep pyright happy

    return AddonListForSettings(
        addons=addons,
        inherited_addons=list(inherited_addons) if project_bundle_name else [],
        bundle_name=project_bundle_name or studio_bundle_name,
        project_name=project_name,
        is_project_bundle=bool(project_bundle_name),
    )

__all__ = ["get_addon_list_for_settings", "AddonListForSettings"]

from typing import TypedDict

from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger


class AddonListForSettings(TypedDict):
    addons: dict[str, str]
    inherited_addons: list[str]
    bundle_name: str


async def get_addon_list_for_settings(
    bundle_name: str | None = None,
    project_name: str | None = None,
    project_bundle_name: str | None = None,
    variant: str = "production",
) -> AddonListForSettings:
    # Get the studio bundle

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

    bundle_name = brow[0]["name"]
    addons: dict[str, str] = brow[0]["addons"]  # {addon_name: addon_version}
    logger.trace(f"Got studio bundle {bundle_name}")

    # Check if there's a project bundle available
    # and get its name

    if (
        project_name
        and (not project_bundle_name)
        and variant in ("production", "staging")
    ):
        r = await Postgres.fetch(
            "SELECT data->'bundle' as bundle FROM projects WHERE name = $1",
            project_name,
        )
        if not r:
            raise NotFoundException(status_code=404, detail="Project not found")
        try:
            project_bundle_name = r[0]["bundle"][variant]
            logger.trace(f"Got project bundle {project_bundle_name}")
        except Exception:
            project_bundle_name = None

    inherited_addons: set[str] = set(addons.keys())

    # Load the project bundle and merge it with the studio bundle

    if project_bundle_name:
        r = await Postgres.fetch(
            """
            SELECT data->'addons' as addons FROM bundles
            WHERE name = $1 AND coalesce((data->'is_project')::boolean, false)
            """,
            project_bundle_name,
        )
        if not r:
            raise NotFoundException(
                status_code=404,
                detail=f"Project bundle {project_bundle_name} not found"
                f"Studio {variant} bundle is not set",
            )

        project_addons = r[0]["addons"]
        for addon_name, addon_version in project_addons.items():
            addons[addon_name] = addon_version
            inherited_addons.remove(addon_name)

    assert (
        bundle_name is not None
    ), "Bundle name is None"  # won't happen, keep pyright happy

    return AddonListForSettings(
        addons=addons,
        inherited_addons=list(inherited_addons) if project_bundle_name else [],
        bundle_name=project_bundle_name or bundle_name,
    )

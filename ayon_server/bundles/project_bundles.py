from typing import Literal

from ayon_server.addons.library import AddonLibrary
from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import Platform


def get_project_bundle_name(
    project_name: str,
    variant: Literal["production", "staging"],
) -> str:
    """Get project bundle name based on project name and variant"""
    return f"__project__{project_name}__{variant}"


async def has_project_bundle(
    project_name: str, variant: Literal["production", "staging"]
) -> bool:
    """Check if the project uses a project bundle for the given variant"""

    query = """
        SELECT 1 FROM public.projects
        WHERE name = $1 AND data->'bundle'->>$2 IS NOT NULL
    """
    result = await Postgres.fetchrow(query, project_name, variant)
    return result is not None


async def process_addon_settings(
    addon_name: str,
    addon_version: str,
    project_name: str,
    variant: Literal["production", "staging"],
) -> None:
    """Process addon settings for the given project and variant."""

    #
    # Sanity checks
    # If the addon does not exist or does not allow overrides,
    # raise an exception, so the entire transaction is rolled back.
    #

    # if addon is not found, it raises NotFoundException,
    addon = AddonLibrary.addon(addon_name, addon_version)

    if not addon.project_can_override_addon_version:
        raise BadRequestException(
            f"Addon {addon_name} version {addon_version} "
            f"does not allow project overrides"
        )

    # Get the "full" project settings (studio settings + overrides)

    project_settings = await addon.get_project_settings(project_name, variant)
    # TODO: load original overrides so, we can create a change event

    project_settings_dict = project_settings.dict() if project_settings else {}

    # Save the entire object as project settings overrides

    update_query = """
        INSERT INTO settings (addon_name, addon_version, variant, data)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (addon_name, addon_version, variant) DO UPDATE SET
            data = EXCLUDED.data
    """

    await Postgres.execute(
        update_query,
        addon_name,
        addon_version,
        variant,
        project_settings_dict,
    )


async def freeze_project_bundle(
    project_name: str,
    *,
    variant: Literal["production", "staging"] = "production",
    addons: dict[str, str | None] | None = None,
    installer_version: str | None = None,
    dependency_packages: dict[Platform, str | None] | None = None,
) -> None:
    """Freeze project bundle

    - ensures that the bundle for the given project and variant exists
    - update the bundle with the given data
    - copies all project settings to the project and enforce them as overrides
    - sets the project bundle in project data

    """

    addons = addons or {}
    dependency_packages = dependency_packages or {}

    bundle_name = get_project_bundle_name(project_name, variant)

    bundle_data = {
        "addons": addons,
        "installer_version": installer_version,
        "dependency_packages": dependency_packages,
        "is_project": True,
    }

    query = """
        INSERT INTO public.bundles (name, is_production, is_staging, is_dev, data)
        VALUES ($1, FALSE, FALSE, FALSE, $2)
        ON CONFLICT (name) DO UPDATE SET
            is_production = FALSE,
            is_staging = FALSE,
            is_dev = FALSE,
            data = EXCLUDED.data
    """

    async with Postgres.transaction():
        # set project schema explicitly,
        # all operations that use public schema in this transaction
        # must use `public.` prefix in their queries

        await Postgres.set_project_schema(project_name)

        # Ensure well-known project bundle exists / is updated

        await Postgres.execute(
            query,
            bundle_name,
            bundle_data,
        )

        # Enforce all overrides for project settings

        for addon_name, addon_version in addons.items():
            if addon_version is None:
                continue

            await process_addon_settings(
                addon_name,
                addon_version,
                project_name,
                variant,
            )

        # Save bundle reference to project data

        project = await ProjectEntity.load(project_name, for_update=True)
        bundle_info = project.data.get("bundle", {})
        bundle_info[variant] = bundle_name
        project.data["bundle"] = bundle_info
        await project.save()


async def unfreeze_project_bundle(
    project_name: str,
    variant: Literal["production", "staging"],
) -> None:
    """Unfreeze project bundle

    - removes the bundle for the given project and variant
    - removes the project bundle from project data
    """
    bundle_name = get_project_bundle_name(project_name, variant)

    async with Postgres.transaction():
        #
        # Unset project bundle in project data
        #

        project = await ProjectEntity.load(project_name, for_update=True)
        bundle_info = project.data.get("bundle", {})
        bundle_info.pop(variant, None)
        if not bundle_info:
            project.data.pop("bundle", None)
        else:
            project.data["bundle"] = bundle_info
        await project.save()

        #
        # Remove the bundle
        #

        delete_query = "DELETE FROM bundles WHERE name = $1"
        await Postgres.execute(delete_query, bundle_name)

    await Redis.delete_ns("all-settings")

import copy
from typing import Any, Literal

from ayon_server.addons.addon import BaseServerAddon
from ayon_server.addons.library import AddonLibrary
from ayon_server.entities import ProjectEntity
from ayon_server.events.eventstream import EventStream
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.set_addon_settings import set_addon_settings
from ayon_server.types import Platform


def get_project_bundle_name(
    project_name: str,
    variant: Literal["production", "staging"],
) -> str:
    """Get project bundle name based on project name and variant"""
    return f"__project__{project_name}__{variant}"


async def has_project_bundle(
    project_name: str,
    variant: Literal["production", "staging"],
) -> bool:
    """Check if the project uses a project bundle for the given variant

    This is used by settings edit endpoint to determine if settings
    should contain the entire model or just overrides.
    """

    query = """
        SELECT 1 FROM public.projects
        WHERE name = $1 AND data->'bundle'->>$2 IS NOT NULL
    """
    result = await Postgres.fetchrow(query, project_name, variant)
    return result is not None


async def get_studio_bundle_addons(
    variant: Literal["production", "staging"],
) -> dict[str, str]:
    """Get the addons for the studio bundle for the given variant"""

    if variant == "production":
        query = "SELECT data FROM public.bundles WHERE is_production"
    else:
        query = "SELECT data FROM public.bundles WHERE is_staging"

    row = await Postgres.fetchrow(query)
    if not row:
        return {}
    return row["data"].get("addons", {})


async def get_project_bundle_addons(project_name: str, variant: str) -> dict[str, str]:
    query = """
        SELECT b.data FROM public.projects p
        JOIN public.bundles b
        ON b.name = p.data->'bundle'->>$2
        WHERE p.name = $1
    """
    row = await Postgres.fetchrow(query, project_name, variant)
    if not row:
        return {}

    return row["data"].get("addons", {})


async def has_project_bundle_addon(
    project_name: str,
    addon_name: str,
    *,
    variant: str = "production",
) -> bool:
    """Checks if the addon is a part of the project bundle for the given project"""
    addons = await get_project_bundle_addons(project_name, variant)

    if not (version := addons.get(addon_name)):
        return False

    if version in ("__inherit__", "__disable__"):
        return False

    return True


async def process_addon_settings(
    addon_name: str,
    addon_version: str,
    project_name: str,
    variant: Literal["production", "staging"],
) -> dict[str, Any] | None:
    """Process addon settings for the given project and variant."""

    #
    # Sanity checks
    # If the addon does not exist or does not allow overrides,
    # raise an exception, so the entire transaction is rolled back.
    #

    if addon_version == "__inherit__":
        return None

    # if addon is not found, it raises NotFoundException,
    addon = AddonLibrary.addon(addon_name, addon_version)

    if not addon.project_can_override_addon_version:
        raise BadRequestException(
            f"Addon {addon_name} version {addon_version} "
            f"does not allow project overrides"
        )

    if not addon.get_settings_model():
        return None

    # Get the "full" project settings (studio settings + overrides)

    project_settings = await addon.get_project_settings(project_name, variant)
    # TODO: load original overrides so, we can create a change event

    project_settings_dict = project_settings.dict() if project_settings else {}

    # Save the entire object as project settings overrides

    return await set_addon_settings(
        addon_name,
        addon_version,
        project_settings_dict,
        project_name=project_name,
        variant=variant,
        send_event=False,
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

    events = []
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

            e = await process_addon_settings(
                addon_name,
                addon_version,
                project_name,
                variant,
            )

            if e:
                events.append(e)

        # Save bundle reference to project data

        project = await ProjectEntity.load(project_name, for_update=True)
        bundle_info = project.data.get("bundle", {})
        bundle_info[variant] = bundle_name
        project.data["bundle"] = bundle_info
        await project.save()
        logger.info("Project bundle frozen")

    for event in events:
        await EventStream.dispatch(**event)
    await Redis.delete_ns("all-settings")


async def _remove_studio_overrides_from_project_addon(
    addon: BaseServerAddon,
    project_name: str,
    variant: Literal["production", "staging"],
) -> dict[str, Any] | None:
    """Remove studio overrides from project addon settings

    Returns an event dict if changes were made, None otherwise.

    THIS MUST RUN INSIDE A TRANSACTION THAT SETS THE PROJECT SCHEMA!
    """

    overrides = await addon.get_project_overrides(project_name, variant)
    old_overrides = copy.deepcopy(overrides)

    settings_model = addon.get_settings_model()
    if not (settings_model and overrides):
        return None

    def crawl(override_obj: dict[str, Any], model: type[BaseSettingsModel]) -> None:
        dict_keys = list(override_obj.keys())
        for key in dict_keys:
            field = model.__fields__.get(key)
            if not field:
                continue

            scopes = field.field_info.extra.get("scope", ["studio", "project"])
            if "project" not in scopes:
                # Field is not project-overridable, remove it
                override_obj.pop(key)
                continue

            try:
                field_type = field.type_

                if issubclass(field_type, BaseSettingsModel):
                    if isinstance(override_obj[key], dict):
                        crawl(override_obj[key], field_type)
            except Exception:
                pass

    crawl(overrides, settings_model)

    if overrides == old_overrides:
        return None

    return await set_addon_settings(
        addon.name,
        addon.version,
        overrides,
        project_name=project_name,
        variant=variant,
        send_event=False,
    )


async def unfreeze_project_bundle(
    project_name: str,
    variant: Literal["production", "staging"],
) -> None:
    """Unfreeze project bundle

    - removes the bundle for the given project and variant
    - removes the project bundle from project data
    """
    bundle_name = get_project_bundle_name(project_name, variant)

    events = []
    async with Postgres.transaction():
        project_bundle_addons = await get_project_bundle_addons(project_name, variant)
        studio_bundle_addons = await get_studio_bundle_addons(variant)

        # From every not-inherited addon in the project bundle,
        # remove studio settings from project overrides

        for addon_name, addon_version in project_bundle_addons.items():
            if not addon_version:
                continue

            if addon_version in ("__inherit__", "__disabled__"):
                continue

            try:
                addon = AddonLibrary.addon(addon_name, addon_version)
            except Exception:
                continue

            res = await _remove_studio_overrides_from_project_addon(
                addon,
                project_name,
                variant,
            )

            if res:
                events.append(res)

            studio_addon_version = studio_bundle_addons.get(addon_name)
            if not studio_addon_version:
                continue

            if studio_addon_version == addon_version:
                # no need to migrate, same version
                continue

            # Migrate the project settings to studio bundle addon versions
            # Refetch the overrides, but use migration logic

            try:
                studio_addon = AddonLibrary.addon(addon_name, studio_addon_version)
            except Exception:
                logger.warning(
                    f"Studio addon {addon_name} {studio_addon_version} not found, "
                    f"skipping migration of project overrides for this addon"
                )
                continue

            if addon.get_settings_model() and studio_addon.get_settings_model():
                logger.trace(f"Migrating project overrides for addon {addon_name}")
                new_overrides = await addon.get_project_overrides(
                    project_name,
                    variant,
                    as_version=studio_addon_version,
                )

                event = await set_addon_settings(
                    addon.name,
                    studio_addon_version,
                    new_overrides,
                    project_name=project_name,
                    variant=variant,
                    send_event=False,
                )

                if event:
                    events.append(event)

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

        delete_query = "DELETE FROM public.bundles WHERE name = $1"
        await Postgres.execute(delete_query, bundle_name)

    for event in events:
        await EventStream.dispatch(**event)
    await Redis.delete_ns("all-settings")

import asyncio
from typing import Annotated, Literal

from fastapi import Query
from pydantic import Field

from ayon_server.addons.library import AddonLibrary
from ayon_server.api.dependencies import CurrentUser, ProjectName, Sender, SenderType
from ayon_server.api.responses import EmptyResponse
from ayon_server.bundles.project_bundles import (
    freeze_project_bundle,
    unfreeze_project_bundle,
)
from ayon_server.entities import ProjectEntity
from ayon_server.enum import EnumItem
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.installer.common import (
    list_dependency_packages,
    list_installer_versions,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import OPModel, Platform

from .router import router


class ProjectBundleModel(OPModel):
    production: str | None = None
    staging: str | None = None


@router.post("/projects/{project_name}/bundles", status_code=204, deprecated=True)
async def set_project_bundles(
    user: CurrentUser,
    project_name: ProjectName,
    payload: ProjectBundleModel,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Set project bundle

    Deprecated: Use the freeze_project_bundle function instead.
    """
    _ = sender, sender_type

    if not user.is_manager:
        raise ForbiddenException("Only managers can set project bundle")

    async with Postgres.transaction():
        project = await ProjectEntity.load(project_name, for_update=True)

        bundle_data = project.data.get("bundle", {})
        bundle_data.update(payload.dict(exclude_unset=True))
        if not bundle_data:
            project.data.pop("bundle", None)
        else:
            project.data["bundle"] = bundle_data
        await project.save()
        await Redis.delete_ns("all-settings")

    return EmptyResponse()


#
# Project bundle management
#

BundleVariant = Annotated[
    Literal["production", "staging"],
    Query(title="Bundle Variant", alias="variant"),
]


class AddonMetadata(OPModel):
    name: Annotated[
        str,
        Field(title="Addon Name"),
    ]
    label: Annotated[
        str,
        Field(title="Addon Label"),
    ]
    options: Annotated[
        list[EnumItem],
        Field(title="Addon Options"),
    ]


class ProjectBundle(OPModel):
    addons: Annotated[
        dict[str, str | None],
        Field(
            title="Addons",
            description=(
                "Dictionary of addon names and their versions. "
                "Use `null` to disable an addon."
            ),
        ),
    ]

    installer_version: Annotated[
        str | None,
        Field(title="Installer Version"),
    ] = None

    dependency_packages: Annotated[
        dict[Platform, str | None] | None,
        Field(title="Platform"),
    ] = None

    addon_metadata: Annotated[
        list[AddonMetadata],
        Field(title="Addon Metadata", default_factory=list),
    ]

    installer_options: Annotated[
        list[str],
        Field(title="Installer Options", default_factory=list),
    ]

    dependency_package_options: Annotated[
        dict[Platform, list[str]],
        Field(title="Dependency Package Options", default_factory=dict),
    ]


@router.post("/projects/{project_name}/bundle")
async def set_project_bundle(
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
    payload: ProjectBundle,
    variant: BundleVariant = "production",
) -> None:
    """Set project bundle"""
    if not user.is_manager:
        raise ForbiddenException("Only managers can set project bundle")

    _ = sender, sender_type

    for addon_name, addon_version in payload.addons.items():
        if addon_version == "__disable__":
            payload.addons[addon_name] = None

    return await freeze_project_bundle(
        project_name,
        variant=variant,
        addons=payload.addons,
        installer_version=payload.installer_version,
        dependency_packages=payload.dependency_packages,
    )


@router.delete("/projects/{project_name}/bundle", status_code=204)
async def unset_project_bundle(
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
    variant: BundleVariant = "production",
) -> None:
    """Unset project bundle"""
    if not user.is_manager:
        raise ForbiddenException("Only managers can unset project bundle")

    _ = sender, sender_type

    return await unfreeze_project_bundle(
        project_name,
        variant=variant,
    )


#
# Project bundle information
#


async def _get_project_bundle_addon_info(
    project_name: str, variant: str
) -> ProjectBundle:
    #
    # Get the base bundle
    #

    if variant == "production":
        query = "SELECT name, data FROM public.bundles WHERE is_production"
    else:
        query = "SELECT name, data FROM public.bundles WHERE is_staging"

    bundle_record = await Postgres.fetchrow(query)
    if not bundle_record:
        raise NotFoundException(f"{variant} bundle is not set")

    base_addons = bundle_record["data"].get("addons", {})
    dependency_packages = bundle_record["data"].get("dependency_packages", {})
    installer_version = bundle_record["data"].get("installer_version")

    #
    # Get the project bundle if exists
    #

    query = """
        SELECT b.name, b.data
        FROM public.bundles b
        JOIN public.projects p
            ON b.name = p.data->'bundle'->>$2
        WHERE p.name = $1
        AND coalesce((b.data->'is_project')::boolean, false)
    """
    project_bundle_record = await Postgres.fetchrow(
        query,
        project_name,
        variant,
    )

    project_addons: dict[str, str | None] | None = None
    if project_bundle_record:
        project_addons = project_bundle_record["data"].get("addons", {})
        # always overwrite dependency packages and installer version from project bundle
        dependency_packages = project_bundle_record["data"].get(
            "dependency_packages", {}
        )
        installer_version = project_bundle_record["data"].get("installer_version")

    addons = {}
    addon_metadata: list[AddonMetadata] = []

    for addon_name, addon_definition in AddonLibrary.items():
        base_version = base_addons.get(addon_name)
        base_version_label = base_version or "DISABLED"

        if not addon_definition.project_can_override_addon_version:
            continue

        if project_addons is not None:
            # we have project bundle

            addon_version = project_addons.get(addon_name)
            if addon_version is None:
                # disabled in project bundle
                addons[addon_name] = "__disable__"
            else:
                addons[addon_name] = addon_version

        else:
            # no project bundle, we show studio versions as default
            v = base_addons.get(addon_name)
            if not v:
                addons[addon_name] = "__disable__"
            else:
                try:
                    a = AddonLibrary.addon(addon_name, v)
                    if a.project_can_override_addon_version:
                        addons[addon_name] = v
                    else:
                        addons[addon_name] = "__inherit__"
                except NotFoundException:
                    addons[addon_name] = "__disable__"

        options = [
            EnumItem(value="__inherit__", label=f"Inherit ({base_version_label})"),
            EnumItem(value="__disable__", label="Disable"),
        ]

        available_versions = []
        for version in addon_definition.versions.values():
            enum_item = EnumItem(
                value=version.version,
                label=version.version,
            )
            if not version.project_can_override_addon_version:
                enum_item.disabled = True
                enum_item.disabled_message = (
                    "This version cannot be used in project bundles."
                )
            available_versions.append(enum_item)

        available_versions.sort(key=lambda x: x.value, reverse=True)
        options.extend(available_versions)

        addon_metadata.append(
            AddonMetadata(
                name=addon_name,
                label=addon_definition.friendly_name,
                options=options,
            )
        )

    return ProjectBundle(
        addons=addons,
        addon_metadata=addon_metadata,
        installer_version=installer_version,
        dependency_packages=dependency_packages,
        installer_options=[],
        dependency_package_options={},
    )


@router.get("/projects/{project_name}/bundle")
async def get_project_bundle_info(
    user: CurrentUser,
    project_name: ProjectName,
    variant: BundleVariant = "production",
) -> ProjectBundle:
    """Get project bundle information"""

    if not user.is_manager:
        raise ForbiddenException("Only managers can get project bundle information")

    async with asyncio.TaskGroup() as tg:
        task_addon_info = tg.create_task(
            _get_project_bundle_addon_info(project_name, variant)
        )
        task_installer_versions = tg.create_task(list_installer_versions())
        task_dependency_packages = tg.create_task(list_dependency_packages())

    result = task_addon_info.result()
    result.installer_options = task_installer_versions.result()
    result.dependency_package_options = task_dependency_packages.result()

    return result

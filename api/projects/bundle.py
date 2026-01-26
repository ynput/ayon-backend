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


class ProjectBundleModel(OPModel):
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


@router.post("/projects/{project_name}/bundle")
async def set_project_bundle(
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
    payload: ProjectBundleModel,
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


@router.get("/projects/{project_name}/bundle")
async def get_project_bundle_info(
    user: CurrentUser,
    project_name: ProjectName,
    variant: BundleVariant = "production",
) -> ProjectBundleModel:
    """Get project bundle information"""

    if not user.is_manager:
        raise ForbiddenException("Only managers can get project bundle information")

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

    addons = {}
    addon_metadata: list[AddonMetadata] = []

    for addon_name, addon_definition in AddonLibrary.items():
        base_version = base_addons.get(addon_name)
        base_version_label = base_version or "DISABLED"

        if not addon_definition.project_can_override_addon_version:
            print("Skipping", addon_name)
            continue

        if project_addons is not None:
            # we have project bundle

            addon_version = project_addons.get(addon_name)
            if addon_version is None:
                # disabled in project bundle
                addons[addon_name] = "__disable__"
            else:
                addons[addon_name] = addon_version

        options = [
            EnumItem(value="__inherit__", label=f"Inherit ({base_version_label})"),
            EnumItem(value="__disable__", label="Disable"),
        ]

        available_versions = sorted(
            addon_definition.versions.keys(),
            reverse=True,
        )
        for version in available_versions:
            options.append(
                EnumItem(
                    value=version,
                    label=version,
                )
            )

        addon_metadata.append(
            AddonMetadata(
                name=addon_name,
                label=addon_definition.friendly_name,
                options=options,
            )
        )

    return ProjectBundleModel(
        addons=addons,
        addon_metadata=addon_metadata,
    )

from typing import Annotated, Literal

from fastapi import Query
from pydantic import Field

from ayon_server.api.dependencies import CurrentUser, ProjectName, Sender, SenderType
from ayon_server.api.responses import EmptyResponse
from ayon_server.bundles.project_bundles import (
    freeze_project_bundle,
    unfreeze_project_bundle,
)
from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import ForbiddenException
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


class SetProjectBundleRequest(OPModel):
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


@router.post("/projects/{project_name}/bundle")
async def set_project_bundle(
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
    payload: SetProjectBundleRequest,
    variant: BundleVariant = "production",
) -> None:
    """Set project bundle"""
    if not user.is_manager:
        raise ForbiddenException("Only managers can set project bundle")

    _ = sender, sender_type

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

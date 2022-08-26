from typing import Any

from addons.router import router
from fastapi import Depends, Response
from nxtools import logging
from pydantic.error_wrappers import ValidationError

from openpype.addons import AddonLibrary
from openpype.api.dependencies import dep_current_user, dep_project_name
from openpype.entities import ProjectEntity, UserEntity
from openpype.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from openpype.lib.postgres import Postgres
from openpype.settings import extract_overrides, list_overrides
from .common import ModifyOverridesRequestModel, remove_override


@router.get("/{addon_name}/{version}/settings/{project_name}", tags=["Addon settings"])
async def get_addon_project_settings(
    addon_name: str,
    version: str,
    project_name: str,
):
    # TODO: enable authentication
    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")
    return await addon.get_project_settings(project_name)


@router.get("/{addon_name}/{version}/overrides/{project_name}", tags=["Addon settings"])
async def get_addon_project_overrides(
    addon_name: str,
    version: str,
    project_name: str,
):
    # TODO: enable authentication
    addon = AddonLibrary.addon(addon_name, version)
    studio_settings = await addon.get_studio_settings()
    if studio_settings is None:
        return {}
    studio_overrides = await addon.get_studio_overrides()
    project_settings = await addon.get_project_settings(project_name)
    project_overrides = await addon.get_project_overrides(project_name)

    result = list_overrides(studio_settings, studio_overrides, level="studio")

    for k, v in list_overrides(
        project_settings, project_overrides, level="project"
    ).items():
        result[k] = v

    return result


@router.post("/{addon_name}/{version}/settings/{project_name}", tags=["Addon settings"])
async def set_addon_project_settings(
    payload: dict[str, Any],
    addon_name: str,
    version: str,
    project_name: str,
    user: UserEntity = Depends(dep_current_user),
):
    """Set the studio overrides of the given addon."""

    if not user.is_manager:
        raise ForbiddenException

    addon = AddonLibrary.addon(addon_name, version)
    original = await addon.get_project_settings(project_name)
    existing = await addon.get_project_overrides(project_name)
    model = addon.get_settings_model()
    if (original is None) or (model is None):
        # This addon does not have settings
        return Response(status_code=400)
    try:
        data = extract_overrides(original, model(**payload), existing)
    except ValidationError:
        raise BadRequestException

    # Do not use versioning during the development (causes headaches)
    await Postgres.execute(
        f"""
        DELETE FROM project_{project_name}.settings
        WHERE addon_name = $1 AND addon_version = $2
        """,
        addon_name,
        version,
    )

    await Postgres.execute(
        f"""
        INSERT INTO project_{project_name}.settings (addon_name, addon_version, data)
        VALUES ($1, $2, $3)
        """,
        addon_name,
        version,
        data,
    )
    return Response(status_code=204)


@router.delete(
    "/{addon_name}/{version}/overrides/{project_name}",
    tags=["Addon settings"],
)
async def delete_addon_project_overrides(
    addon_name: str,
    version: str,
    #    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    # TODO: enable authentication

    #    if not user.is_manager:
    #        raise ForbiddenException

    logging.info(
        f"Deleting {project_name} project overrides for {addon_name} {version}"
    )

    # Ensure the addon and the project exist
    _ = AddonLibrary.addon(addon_name, version)
    _ = ProjectEntity.load(project_name)

    # we don't use versioned settings at the moment.
    # in the future, insert an empty dict instead
    await Postgres.execute(
        f"""
        DELETE FROM project_{project_name}.settings
        WHERE addon_name = $1
        AND addon_version = $2
        """,
        addon_name,
        version,
    )
    return Response(status_code=204)


@router.post(
    "/{addon_name}/{version}/overrides/{project_name}", tags=["Addon settings"],
)
async def modify_overrides(
    payload: ModifyOverridesRequestModel,
    addon_name: str,
    version: str,
    project_name: str,
    user: UserEntity = Depends(dep_current_user),
):
    if not user.is_manager:
        raise ForbiddenException

    await remove_override(addon_name, version, payload.path, project_name)
    return Response(status_code=204)

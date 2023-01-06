from typing import Any

from addons.router import route_meta, router
from fastapi import Depends, Response
from nxtools import logging
from pydantic.error_wrappers import ValidationError

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import dep_current_user, dep_project_name
from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.settings import (
    extract_overrides,
    list_overrides,
    postprocess_settings_schema,
)

from .common import ModifyOverridesRequestModel, pin_override, remove_override


@router.get("/{addon_name}/{version}/schema/{project_name}", **route_meta)
async def get_addon_settings_schema(
    addon_name: str,
    version: str,
    project_name: str = Depends(dep_project_name),
    user: UserEntity = Depends(dep_current_user),
):
    """Return the JSON schema of the addon settings."""

    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")

    model = addon.get_settings_model()

    if model is None:
        logging.error(f"No settings schema for addon {addon_name}")
        return {}

    context = {
        "project_name": project_name,
    }

    schema = model.schema()
    await postprocess_settings_schema(schema, model, context=context)
    schema["title"] = addon.friendly_name
    return schema


@router.get("/{addon_name}/{version}/settings/{project_name}", **route_meta)
async def get_addon_project_settings(
    addon_name: str,
    version: str,
    project_name: str,
    user: UserEntity = Depends(dep_current_user),
):
    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")
    return await addon.get_project_settings(project_name)


@router.get("/{addon_name}/{version}/overrides/{project_name}", **route_meta)
async def get_addon_project_overrides(
    addon_name: str,
    version: str,
    project_name: str,
    user: UserEntity = Depends(dep_current_user),
):
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


@router.post("/{addon_name}/{version}/settings/{project_name}", **route_meta)
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


@router.delete("/{addon_name}/{version}/overrides/{project_name}", **route_meta)
async def delete_addon_project_overrides(
    addon_name: str,
    version: str,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    if not user.is_manager:
        raise ForbiddenException

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


@router.post("/{addon_name}/{version}/overrides/{project_name}", **route_meta)
async def modify_project_overrides(
    payload: ModifyOverridesRequestModel,
    addon_name: str,
    version: str,
    project_name: str,
    user: UserEntity = Depends(dep_current_user),
):
    if not user.is_manager:
        raise ForbiddenException

    if payload.action == "delete":
        await remove_override(addon_name, version, payload.path, project_name)
    elif payload.action == "pin":
        await pin_override(addon_name, version, payload.path, project_name)
    return Response(status_code=204)

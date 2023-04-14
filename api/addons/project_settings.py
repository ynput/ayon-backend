from typing import Any

from addons.router import route_meta, router
from fastapi import Query
from nxtools import logging
from pydantic.error_wrappers import ValidationError

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.config import ayonconfig
from ayon_server.entities import ProjectEntity
from ayon_server.events import dispatch_event
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

from .common import (
    ModifyOverridesRequestModel,
    pin_override,
    pin_site_override,
    remove_override,
    remove_site_override,
)


@router.get("/{addon_name}/{version}/schema/{project_name}", **route_meta)
async def get_addon_project_settings_schema(
    addon_name: str,
    version: str,
    project_name: ProjectName,
    user: CurrentUser,
    site: str | None = Query(None, regex="^[a-z0-9-]+$"),
) -> dict[str, Any]:
    """Return the JSON schema of the addon settings."""

    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")

    model = addon.get_settings_model()

    if model is None:
        logging.error(f"No settings schema for addon {addon_name}")
        return {}

    context = {
        "project_name": project_name,
        "site_id": site,
        "user_name": user.name,
    }

    schema = model.schema()
    await postprocess_settings_schema(schema, model, context=context)
    schema["title"] = addon.friendly_name
    return schema


@router.get("/{addon_name}/{version}/settings/{project_name}", **route_meta)
async def get_addon_project_settings(
    addon_name: str,
    version: str,
    project_name: ProjectName,
    user: CurrentUser,
    variant: str = Query("production"),
    site: str | None = Query(None, regex="^[a-z0-9-]+$"),
) -> dict[str, Any]:
    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")

    if site:
        return await addon.get_project_site_settings(project_name, user.name, site)

    return await addon.get_project_settings(project_name, variant=variant)


@router.get("/{addon_name}/{version}/overrides/{project_name}", **route_meta)
async def get_addon_project_overrides(
    addon_name: str,
    version: str,
    project_name: ProjectName,
    user: CurrentUser,
    variant: str = Query("production"),
    site: str | None = Query(None, regex="^[a-z0-9-]+$"),
):
    addon = AddonLibrary.addon(addon_name, version)
    studio_settings = await addon.get_studio_settings(variant=variant)
    if studio_settings is None:
        return {}
    studio_overrides = await addon.get_studio_overrides(variant=variant)
    project_settings = await addon.get_project_settings(project_name, variant=variant)
    project_overrides = await addon.get_project_overrides(project_name, variant=variant)

    result = list_overrides(studio_settings, studio_overrides, level="studio")

    for k, v in list_overrides(
        project_settings, project_overrides, level="project"
    ).items():
        result[k] = v

    if site:
        site_overrides = await addon.get_project_site_overrides(
            project_name, user.name, site
        )
        site_settings = await addon.get_project_site_settings(
            project_name, user.name, site
        )
        for k, v in list_overrides(site_settings, site_overrides, level="site").items():
            result[k] = v

    return result


@router.post(
    "/{addon_name}/{version}/settings/{project_name}", status_code=204, **route_meta
)
async def set_addon_project_settings(
    payload: dict[str, Any],
    addon_name: str,
    version: str,
    project_name: ProjectName,
    user: CurrentUser,
    variant: str = Query("production"),
    site: str | None = Query(None, regex="^[a-z0-9-]+$"),
) -> EmptyResponse:
    """Set the studio overrides of the given addon."""

    addon = AddonLibrary.addon(addon_name, version)
    model = addon.get_settings_model()
    if model is None:
        raise BadRequestException(f"Addon {addon_name} has no settings")

    if not site:
        if not user.is_manager:
            raise ForbiddenException

        original = await addon.get_project_settings(project_name)
        existing = await addon.get_project_overrides(project_name)
        if original is None:
            # This addon does not have settings
            raise BadRequestException(f"Addon {addon_name} has no settings")
        try:
            data = extract_overrides(original, model(**payload), existing)
        except ValidationError:
            raise BadRequestException

        await Postgres.execute(
            f"""
            INSERT INTO project_{project_name}.settings
            (addon_name, addon_version, variant, data)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (addon_name, addon_version, variant) DO UPDATE
            SET data = $4
            """,
            addon_name,
            version,
            variant,
            data,
        )

        if ayonconfig.audit_trail:
            payload = {
                "originalValue": existing,
                "newValue": data,
            }
        else:
            payload = None

        await dispatch_event(
            topic="settings.changed",
            description=f"{addon_name}:{version} project overrides changed",
            summary={
                "addon_name": addon_name,
                "addon_version": version,
                "variant": variant,
            },
            user=user.name,
            project=project_name,
            payload=payload,
        )

        return EmptyResponse()

    # site settings

    original = await addon.get_project_site_settings(project_name, user.name, site)
    existing = await addon.get_project_site_overrides(project_name, user.name, site)
    if original is None:
        # This addon does not have settings
        raise BadRequestException(f"Addon {addon_name} has no settings")
    try:
        data = extract_overrides(original, model(**payload), existing)
    except ValidationError:
        raise BadRequestException

    await Postgres.execute(
        f"""
        INSERT INTO project_{project_name}.project_site_settings
        (addon_name, addon_version, site_id, user_name, data)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (addon_name, addon_version, site_id, user_name)
        DO UPDATE SET data = $5
        """,
        addon_name,
        version,
        site,
        user.name,
        data,
    )
    return EmptyResponse()


@router.delete("/{addon_name}/{version}/overrides/{project_name}", **route_meta)
async def delete_addon_project_overrides(
    addon_name: str,
    version: str,
    user: CurrentUser,
    project_name: ProjectName,
    variant: str = Query("production"),
    site: str | None = Query(None, regex="^[a-z0-9-]+$"),
):
    # Ensure the addon and the project exist
    _ = AddonLibrary.addon(addon_name, version)
    _ = await ProjectEntity.load(project_name)

    if not site:
        if not user.is_manager:
            raise ForbiddenException

        await Postgres.execute(
            f"""
            DELETE FROM project_{project_name}.settings
            WHERE addon_name = $1
            AND addon_version = $2
            AND variant = $3
            """,
            addon_name,
            version,
            variant,
        )

        await dispatch_event(
            topic="settings.deleted",
            description=f"{addon_name}:{version} project overrides deleted",
            summary={
                "addon_name": addon_name,
                "addon_version": version,
                "variant": variant,
            },
            user=user.name,
            project=project_name,
        )

        return EmptyResponse()

    # site settings

    await Postgres.execute(
        f"""
        DELETE FROM project_{project_name}.project_site_settings
        WHERE addon_name = $1
        AND addon_version = $2
        AND site_id = $3
        AND user_name = $4
        """,
        addon_name,
        version,
        site,
        user.name,
    )
    return EmptyResponse()


@router.post("/{addon_name}/{version}/overrides/{project_name}", **route_meta)
async def modify_project_overrides(
    payload: ModifyOverridesRequestModel,
    addon_name: str,
    version: str,
    project_name: str,
    user: CurrentUser,
    variant: ProjectName,
    site: str | None = Query(None, regex="^[a-z0-9-]+$"),
):

    if site:
        if payload.action == "delete":
            await remove_site_override(
                addon_name,
                version,
                project_name,
                site,
                user.name,
                payload.path,
            )

        elif payload.action == "pin":
            await pin_site_override(
                addon_name,
                version,
                project_name,
                site,
                user.name,
                payload.path,
            )

        return EmptyResponse()

    if not user.is_manager:
        raise ForbiddenException

    if payload.action == "delete":
        await remove_override(
            addon_name,
            version,
            payload.path,
            project_name=project_name,
            variant=variant,
        )
    elif payload.action == "pin":
        await pin_override(
            addon_name,
            version,
            payload.path,
            project_name=project_name,
            variant=variant,
        )
    return EmptyResponse()

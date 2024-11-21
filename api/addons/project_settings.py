import copy
from typing import Any

from fastapi import Query
from nxtools import logging
from pydantic.error_wrappers import ValidationError

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser, ProjectName, SiteID
from ayon_server.api.responses import EmptyResponse
from ayon_server.config import ayonconfig
from ayon_server.entities import ProjectEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.settings import BaseSettingsModel
from ayon_server.settings.overrides import extract_overrides, list_overrides
from ayon_server.settings.postprocess import postprocess_settings_schema

from .common import (
    ModifyOverridesRequestModel,
    pin_override,
    pin_site_override,
    remove_override,
    remove_site_override,
)
from .router import route_meta, router


@router.get("/{addon_name}/{version}/schema/{project_name}", **route_meta)
async def get_addon_project_settings_schema(
    addon_name: str,
    version: str,
    project_name: ProjectName,
    user: CurrentUser,
    site_id: SiteID,
    variant: str = Query("production"),
) -> dict[str, Any]:
    """Return the JSON schema of the addon settings."""

    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")

    model = addon.get_settings_model()

    if model is None:
        logging.error(f"No settings schema for addon {addon_name}")
        return {}

    context = {
        "addon": addon,
        "project_name": project_name,
        "settings_variant": variant,
        "site_id": site_id,
        "user_name": user.name,
    }

    schema = copy.deepcopy(model.schema())
    await postprocess_settings_schema(schema, model, context=context)
    schema["title"] = addon.friendly_name
    return schema


@router.get(
    "/{addon_name}/{version}/settings/{project_name}",
    response_model=dict[str, Any],
    **route_meta,
)
async def get_addon_project_settings(
    addon_name: str,
    version: str,
    project_name: ProjectName,
    user: CurrentUser,
    site_id: SiteID,
    variant: str = Query("production"),
    as_version: str | None = Query(None, alias="as"),
) -> BaseSettingsModel:
    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")

    if site_id:
        settings = await addon.get_project_site_settings(
            project_name, user.name, site_id, variant=variant, as_version=as_version
        )
    else:
        settings = await addon.get_project_settings(
            project_name, variant=variant, as_version=as_version
        )

    if not settings:
        raise NotFoundException(f"Settings for {addon_name} {version} not found")
    return settings


@router.get("/{addon_name}/{version}/overrides/{project_name}", **route_meta)
async def get_addon_project_overrides(
    addon_name: str,
    version: str,
    project_name: ProjectName,
    user: CurrentUser,
    site_id: SiteID,
    variant: str = Query("production"),
    as_version: str | None = Query(None, alias="as"),
):
    addon = AddonLibrary.addon(addon_name, version)
    studio_settings = await addon.get_studio_settings(
        variant=variant,
        as_version=as_version,
    )
    if studio_settings is None:
        return {}
    studio_overrides = await addon.get_studio_overrides(
        variant=variant,
        as_version=as_version,
    )
    project_settings = await addon.get_project_settings(
        project_name,
        variant=variant,
        as_version=as_version,
    )
    project_overrides = await addon.get_project_overrides(
        project_name,
        variant=variant,
        as_version=as_version,
    )

    result: dict[str, BaseSettingsModel | None] = {}
    result = list_overrides(studio_settings, studio_overrides, level="studio")

    if project_settings:
        for k, v in list_overrides(
            project_settings,
            project_overrides,
            level="project",
        ).items():
            result[k] = v

    if site_id:
        site_overrides = await addon.get_project_site_overrides(
            project_name,
            user.name,
            site_id,
            as_version=as_version,
        )
        site_settings = await addon.get_project_site_settings(
            project_name,
            user.name,
            site_id,
            as_version=as_version,
        )
        if site_settings:
            for k, v in list_overrides(
                site_settings, site_overrides, level="site"
            ).items():
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
    site_id: SiteID,
    variant: str = Query("production"),
) -> EmptyResponse:
    """Set the project overrides of the given addon."""

    addon = AddonLibrary.addon(addon_name, version)
    model = addon.get_settings_model()
    if model is None:
        raise BadRequestException(f"Addon {addon_name} has no settings")

    explicit_pins = payload.pop("__pinned_fields__", None)
    explicit_unpins = payload.pop("__unpinned_fields__", None)

    if not site_id:
        if not user.is_manager:
            raise ForbiddenException

        original = await addon.get_project_settings(project_name, variant=variant)
        existing = await addon.get_project_overrides(project_name, variant=variant)

        if original is None:
            # This addon does not have settings
            raise BadRequestException(f"Addon {addon_name} has no settings")
        try:
            data = extract_overrides(
                original,
                model(**payload),
                existing=existing,
                explicit_pins=explicit_pins,
                explicit_unpins=explicit_unpins,
            )
        except ValidationError as e:
            raise BadRequestException("Invalid settings", errors=e.errors()) from e

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
            payload = {}

        new_settings = await addon.get_project_settings(project_name, variant=variant)
        if new_settings:
            await addon.on_settings_changed(
                old_settings=original,
                new_settings=new_settings,
                project_name=project_name,
                variant=variant,
            )

        await EventStream.dispatch(
            topic="settings.changed",
            description=f"{addon_name} {version} {variant} project overrides changed",
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

    original = await addon.get_project_site_settings(
        project_name, user.name, site_id, variant=variant
    )
    existing = await addon.get_project_site_overrides(project_name, user.name, site_id)
    if original is None:
        # This addon does not have settings
        raise BadRequestException(f"Addon {addon_name} has no settings")
    try:
        data = extract_overrides(
            original,
            model(**payload),
            existing=existing,
            explicit_pins=explicit_pins,
        )
    except ValidationError:
        raise BadRequestException("Invalid settings") from None

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
        site_id,
        user.name,
        data,
    )

    new_settings = await addon.get_project_site_settings(
        project_name, user.name, site_id, variant=variant
    )
    if new_settings:
        await addon.on_settings_changed(
            old_settings=original,
            new_settings=new_settings,
            project_name=project_name,
            variant=variant,
            site_id=site_id,
            user_name=user.name,
        )

    # TODO: Audit trail / events

    return EmptyResponse()


@router.delete(
    "/{addon_name}/{version}/overrides/{project_name}", status_code=204, **route_meta
)
async def delete_addon_project_overrides(
    addon_name: str,
    version: str,
    user: CurrentUser,
    project_name: ProjectName,
    site_id: SiteID,
    variant: str = Query("production"),
):
    # Ensure the addon and the project exist
    addon = AddonLibrary.addon(addon_name, version)
    _ = await ProjectEntity.load(project_name)

    if not site_id:
        if not user.is_manager:
            raise ForbiddenException

        old_settings = await addon.get_project_settings(project_name, variant=variant)
        new_settings = await addon.get_studio_settings(variant=variant)

        res = await Postgres.fetch(
            f"""
            DELETE FROM project_{project_name}.settings
            WHERE addon_name = $1
            AND addon_version = $2
            AND variant = $3
            RETURNING data
            """,
            addon_name,
            version,
            variant,
        )

        if res:
            old_overrides = res[0]["data"]
        else:
            old_overrides = {}

        if new_settings and old_settings:
            await addon.on_settings_changed(
                old_settings=old_settings,
                new_settings=new_settings,
                project_name=project_name,
                variant=variant,
            )

        payload = {}
        if ayonconfig.audit_trail:
            payload = {
                "originalValue": old_overrides,
                "newValue": {},
            }

        await EventStream.dispatch(
            topic="settings.changed",
            description=f"{addon_name} {version} {variant} project overrides removed",
            summary={
                "addon_name": addon_name,
                "addon_version": version,
                "variant": variant,
            },
            payload=payload,
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
        site_id,
        user.name,
    )

    old_settings = await addon.get_project_site_settings(
        project_name, user.name, site_id, variant=variant
    )
    new_settings = await addon.get_project_settings(project_name, variant=variant)

    if new_settings and old_settings:
        await addon.on_settings_changed(
            old_settings=old_settings,
            new_settings=new_settings,
            project_name=project_name,
            variant=variant,
            site_id=site_id,
            user_name=user.name,
        )

    # TODO: Audit trail / events

    return EmptyResponse()


@router.post(
    "/{addon_name}/{version}/overrides/{project_name}", status_code=204, **route_meta
)
async def modify_project_overrides(
    payload: ModifyOverridesRequestModel,
    addon_name: str,
    version: str,
    project_name: ProjectName,
    user: CurrentUser,
    site_id: SiteID,
    variant: str = Query("production"),
):
    addon = AddonLibrary.addon(addon_name, version)
    if not addon:
        raise NotFoundException(f"Addon {addon_name} {version} not found")

    if site_id:
        old_settings = await addon.get_project_site_settings(
            project_name, user.name, site_id, variant=variant
        )

        if payload.action == "delete":
            await remove_site_override(
                addon_name,
                version,
                project_name,
                site_id,
                user.name,
                payload.path,
            )

        elif payload.action == "pin":
            await pin_site_override(
                addon_name,
                version,
                project_name,
                site_id,
                user.name,
                payload.path,
            )

        new_settings = await addon.get_project_site_settings(
            project_name, user.name, site_id, variant=variant
        )

        if new_settings and old_settings:
            await addon.on_settings_changed(
                old_settings=old_settings,
                new_settings=new_settings,
                project_name=project_name,
                variant=variant,
                site_id=site_id,
                user_name=user.name,
            )

        return EmptyResponse()

    if not user.is_manager:
        raise ForbiddenException

    old_settings = await addon.get_project_settings(project_name, variant=variant)
    if ayonconfig.audit_trail:
        old_overrides = await addon.get_project_overrides(
            project_name,
            variant=variant,
        )
    else:
        old_overrides = {}

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

    new_settings = await addon.get_project_settings(project_name, variant=variant)

    if new_settings and old_settings:
        await addon.on_settings_changed(
            old_settings=old_settings,
            new_settings=new_settings,
            project_name=project_name,
            variant=variant,
        )

    event_payload = {}
    if ayonconfig.audit_trail:
        new_overrides = await addon.get_project_overrides(
            project_name,
            variant=variant,
        )
        event_payload = {
            "originalValue": old_overrides,
            "newValue": new_overrides,
        }

    await EventStream.dispatch(
        topic="settings.changed",
        description=f"{addon_name} {version} {variant} project overrides changed",
        summary={
            "addon_name": addon_name,
            "addon_version": version,
            "variant": variant,
        },
        user=user.name,
        project=project_name,
        payload=event_payload,
    )

    return EmptyResponse()


@router.get("/{addon_name}/{addon_version}/rawOverrides/{project_name}", **route_meta)
async def get_raw_addon_project_overrides(
    addon_name: str,
    addon_version: str,
    user: CurrentUser,
    project_name: ProjectName,
    site_id: SiteID,
    variant: str = Query("production"),
) -> dict[str, Any]:
    if site_id:
        result = await Postgres.fetch(
            f"""
            SELECT data FROM project_{project_name}.project_site_settings
            WHERE addon_name = $1
            AND addon_version = $2
            AND site_id = $3
            AND user_name = $4
            """,
            addon_name,
            addon_version,
            site_id,
            user.name,
        )

    elif user.is_admin:
        result = await Postgres.fetch(
            f"""
            SELECT data FROM project_{project_name}.settings
            WHERE addon_name = $1
            AND addon_version = $2
            AND variant = $3
            """,
            addon_name,
            addon_version,
            variant,
        )
    else:
        raise ForbiddenException("Only admins can access raw overrides")

    if not result:
        return {}

    return result[0]["data"]


@router.put(
    "/{addon_name}/{addon_version}/rawOverrides/{project_name}",
    status_code=204,
    **route_meta,
)
async def set_raw_addon_project_overrides(
    addon_name: str,
    addon_version: str,
    payload: dict[str, Any],
    user: CurrentUser,
    project_name: ProjectName,
    site_id: SiteID,
    variant: str = Query("production"),
) -> EmptyResponse:
    """Set raw studio overrides for an addon.

    Warning: this endpoint is not intended for general use and should only be used by
    administrators. It bypasses the normal validation and processing that occurs when
    modifying studio overrides through the normal API.

    It won't trigger any events or validation checks, and may result in unexpected
    behaviour if used incorrectly.
    """

    if site_id:
        await Postgres.execute(
            f"""
            INSERT INTO project_{project_name}.project_site_settings
                (addon_name, addon_version, site_id, user_name, data)
            VALUES
                ($1, $2, $3, $4, $5)
            ON CONFLICT (addon_name, addon_version, site_id, user_name)
                DO UPDATE SET data = $5
            """,
            addon_name,
            addon_version,
            site_id,
            user.name,
            payload,
        )

    elif user.is_admin:
        await Postgres.execute(
            f"""
            INSERT INTO project_{project_name}.settings
                (addon_name, addon_version, variant, data)
            VALUES
                ($1, $2, $3, $4)
            ON CONFLICT (addon_name, addon_version, variant)
                DO UPDATE SET data = $4
            """,
            addon_name,
            addon_version,
            variant,
            payload,
        )
    else:
        raise ForbiddenException("Only admins can access raw overrides")
    return EmptyResponse()

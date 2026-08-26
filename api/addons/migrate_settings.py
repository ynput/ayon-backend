import asyncio
from typing import Any

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.events import EventStream
from ayon_server.exceptions import BadRequestException, ForbiddenException
from ayon_server.helpers.migrate_addon_settings import migrate_addon_settings
from ayon_server.types import Field, OPModel

from .router import router


class MigrateAddonSettingsRequestModel(OPModel):
    source_version: str = Field(..., title="Source addon version")
    target_version: str = Field(..., title="Target addon version")
    source_variant: str = Field("production", title="Source variant")
    target_variant: str = Field("production", title="Target variant")
    with_projects: bool = Field(
        True, title="Migrate project settings as well as studio settings"
    )


class MigrateAddonSettingsResponseModel(OPModel):
    events: list[dict[str, Any]] = Field(
        ..., title="Events created during the migration"
    )


async def _dispatch_events(events: list[dict[str, Any]], user_name: str | None) -> None:
    for event in events:
        event["user"] = user_name
        await EventStream.dispatch("settings.changed", **event)


@router.post("/{addon_name}/migrate")
async def migrate_addon_settings_endpoint(
    user: CurrentUser,
    addon_name: str,
    payload: MigrateAddonSettingsRequestModel,
) -> MigrateAddonSettingsResponseModel:
    """Migrate settings from a source addon version to a target addon version."""

    if not user.is_admin:
        raise ForbiddenException("Only admins can migrate addon settings")

    if payload.source_version == payload.target_version:
        raise BadRequestException("Source and target addon versions must be different")

    source_addon = AddonLibrary.addon(addon_name, payload.source_version)
    target_addon = AddonLibrary.addon(addon_name, payload.target_version)

    events = await migrate_addon_settings(
        source_addon,
        target_addon,
        source_variant=payload.source_variant,
        target_variant=payload.target_variant,
        with_projects=payload.with_projects,
    )

    if events:
        asyncio.create_task(_dispatch_events(events, user.name))

    return MigrateAddonSettingsResponseModel(events=events)

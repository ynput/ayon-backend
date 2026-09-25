from datetime import datetime
from typing import Literal

import shortuuid
from fastapi import BackgroundTasks, Query, Request

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.files import handle_upload
from ayon_server.constraints import Constraints
from ayon_server.events import EventStream
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.download_addon import download_addon
from ayon_server.installer import background_installer
from ayon_server.installer.addons import get_addon_zip_info
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils import hash_data

from .router import router

#
# API
#


class InstallAddonResponseModel(OPModel):
    event_id: str = Field(..., title="Event ID")


@router.post("/install")
async def upload_addon_zip_file(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    request: Request,
    url: str | None = Query(None, title="URL to the addon zip file"),
    addonName: str | None = Query(None, title="Addon name"),
    addonVersion: str | None = Query(None, title="Addon version"),
) -> InstallAddonResponseModel:
    """Upload an addon zip file and install it"""

    # Check if the user is allowed to install addons

    if not user.is_admin:
        raise ForbiddenException("Only admins can install addons")

    if url:
        event_id = await download_addon(url, addonName, addonVersion)
        return InstallAddonResponseModel(event_id=event_id)

    # Store the zip file in a temporary location

    if (
        allow_custom_addons := await Constraints.check("allowCustomAddons")
    ) is not None:
        if not allow_custom_addons:
            raise ForbiddenException("Custom addons uploads are not allowed")

    temp_path = f"/tmp/{shortuuid.uuid()}.zip"
    await handle_upload(request, temp_path)

    # Get addon name and version from the zip file

    zip_info = get_addon_zip_info(temp_path)
    zip_info.zip_path = temp_path

    # We don't create the event before we know that the zip file is valid
    # and contains an addon. If it doesn't, an exception is raised before
    # we reach this point.

    event_hash = hash_data(["addon.install", zip_info.name, zip_info.version])
    event_id = await EventStream.dispatch(
        "addon.install",
        hash=event_hash,
        description=f"Installing addon {zip_info.name} {zip_info.version}",
        summary=zip_info.dict(exclude_none=True),
        user=user.name,
        finished=False,
        reuse=True,
    )

    # Start the installation in the background
    # And return the event ID to the client,
    # so that the client can poll the event status.

    background_tasks.add_task(background_installer.enqueue, event_id)

    return InstallAddonResponseModel(event_id=event_id)


class AddonInstallListItemModel(OPModel):
    id: str = Field(..., title="Addon ID")
    topic: Literal["addon.install", "addon.install_from_url"] = Field(
        ...,
        title="Event topic",
    )
    description: str = Field(..., title="Addon description")
    addon_name: str | None = Field(None, title="Addon name")
    addon_version: str | None = Field(None, title="Addon version")
    user: str | None = Field(None, title="User who installed the addon")
    status: str = Field(..., title="Event status")
    created_at: datetime = Field(..., title="Event creation time")
    updated_at: datetime | None = Field(None, title="Event update time")


class AddonInstallListResponseModel(OPModel):
    items: list[AddonInstallListItemModel] = Field(..., title="List of addons")
    restart_required: bool = Field(...)


@router.get("/install")
async def get_installed_addons_list(
    user: CurrentUser,
) -> AddonInstallListResponseModel:
    """Get a list of installed addons"""

    query = """
        SELECT id, topic, description, summary, user, status, created_at, updated_at
        FROM events WHERE topic IN ('addon.install', 'addon.install_from_url')
        ORDER BY updated_at DESC
        LIMIT 100
    """

    last_change: datetime | None = None
    items = []
    async for row in Postgres.iterate(query):
        summary = row["summary"] or {}
        if last_change is None:
            last_change = row["updated_at"]
        else:
            last_change = max(last_change, row["updated_at"])
        items.append(
            AddonInstallListItemModel(
                id=row["id"],
                topic=row["topic"],
                description=row["description"],
                addon_name=summary.get("name"),
                addon_version=summary.get("version"),
                user=row["user"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )

    # Check if a restart is required
    if last_change is None:
        restart_required = False
    else:
        res = await Postgres.fetch(
            """
                SELECT id FROM events
                WHERE topic = 'server.started'
                AND created_at > $1
                ORDER BY created_at DESC
                LIMIT 1
            """,
            last_change,
        )

        restart_required = not bool(res)

    return AddonInstallListResponseModel(
        items=items,
        restart_required=restart_required,
    )

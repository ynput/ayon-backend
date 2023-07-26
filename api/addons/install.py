import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Literal

import aiofiles
import httpx
import shortuuid
from fastapi import BackgroundTasks, Query, Request
from nxtools import logging

from ayon_server.api.dependencies import CurrentUser
from ayon_server.config import ayonconfig
from ayon_server.events import dispatch_event, update_event
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router


def get_zip_info(path: str) -> tuple[str, str]:
    """Returns the addon name and version from the zip file"""
    with zipfile.ZipFile(path, "r") as zip_ref:
        names = zip_ref.namelist()
        if "manifest.json" not in names:
            raise RuntimeError("Addon manifest not found in zip file")

        if "addon/__init__.py" not in names:
            raise RuntimeError("Addon __init__.py not found in zip file")

        with zip_ref.open("manifest.json") as manifest_file:
            manifest = json.load(manifest_file)

            addon_name = manifest.get("addon_name")
            addon_version = manifest.get("addon_version")

            if not (addon_name and addon_version):
                raise RuntimeError("Addon name or version not found in manifest")
        return addon_name, addon_version


def unpack_addon_sync(zip_path: str, addon_name: str, addon_version) -> None:
    addon_root_dir = ayonconfig.addons_dir
    target_dir = os.path.join(addon_root_dir, addon_name, addon_version)

    with tempfile.TemporaryDirectory(dir=addon_root_dir) as tmpdirname:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(tmpdirname)

        if os.path.isdir(target_dir):
            logging.info(f"Removing existing addon {addon_name} {addon_version}")
            shutil.rmtree(target_dir)

        # move the extracted files to the target directory
        shutil.move(os.path.join(tmpdirname, "addon"), target_dir)


async def unpack_addon(
    event_id: str,
    zip_path: str,
    addon_name: str,
    addon_version: str,
):
    """Unpack the addon from the zip file and install it

    Unpacking is done in a separate thread to avoid blocking the main thread
    (unzipping is a synchronous operation and it is also cpu-bound)

    After the addon is unpacked, the event is finalized and the zip file is removed.
    """

    await update_event(
        event_id,
        description=f"Unpacking addon {addon_name} {addon_version}",
        status="in_progress",
    )

    loop = asyncio.get_event_loop()

    try:
        with ThreadPoolExecutor() as executor:
            task = loop.run_in_executor(
                executor,
                unpack_addon_sync,
                zip_path,
                addon_name,
                addon_version,
            )
            await asyncio.gather(task)
    except Exception as e:
        logging.error(f"Error while unpacking addon: {e}")
        await update_event(
            event_id,
            description=f"Error while unpacking addon: {e}",
            status="failed",
        )

    try:
        os.remove(zip_path)
    except Exception as e:
        logging.error(f"Error while removing zip file: {e}")

    await update_event(
        event_id,
        description=f"Addon {addon_name} {addon_version} installed",
        status="finished",
    )


async def install_addon_from_url(event_id: str, url: str) -> None:
    """Download the addon zip file from the URL and install it"""

    await update_event(
        event_id,
        description=f"Downloading addon from URL {url}",
        status="in_progress",
    )

    # Download the zip file

    with tempfile.NamedTemporaryFile(dir=ayonconfig.addons_dir) as temporary_file:
        zip_path = temporary_file.name
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url) as response:
                async with aiofiles.open(zip_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        await f.write(chunk)

        # Get the addon name and version from the zip file

        addon_name, addon_version = get_zip_info(zip_path)
        await update_event(
            event_id,
            description=f"Installing addon {addon_name} {addon_version}",
            status="in_progress",
            summary={
                "addon_name": addon_name,
                "addon_version": addon_version,
                "url": url,
            },
        )

        # Unpack the addon

        loop = asyncio.get_event_loop()

        try:
            with ThreadPoolExecutor() as executor:
                task = loop.run_in_executor(
                    executor,
                    unpack_addon_sync,
                    zip_path,
                    addon_name,
                    addon_version,
                )
                await asyncio.gather(task)
        except Exception as e:
            logging.error(f"Error while unpacking addon: {e}")
            await update_event(
                event_id,
                description=f"Error while unpacking addon: {e}",
                status="failed",
            )

    await update_event(
        event_id,
        description=f"Addon {addon_name} {addon_version} installed",
        status="finished",
    )


#
# API
#


class InstallAddonResponseModel(OPModel):
    event_id: str = Field(..., title="Event ID")


@router.post("/install", tags=["Addons"])
async def upload_addon_zip_file(
    user: CurrentUser,
    request: Request,
    background_tasks: BackgroundTasks,
    url: str | None = Query(None, title="URL to the addon zip file"),
) -> InstallAddonResponseModel:
    """Upload an addon zip file and install it"""

    # Check if the user is allowed to install addons

    if not user.is_admin:
        raise ForbiddenException("Only admins can install addons")

    if url:
        hash = hashlib.sha256(f"addon_install_{url}".encode("utf-8")).hexdigest()

        query = """
            SELECT id FROM events
            WHERE topic = 'addon.install_from_url'
            AND hash = $1
        """

        res = await Postgres.fetch(query, hash)
        if res:
            event_id = res[0]["id"]
        else:
            event_id = await dispatch_event(
                "addon.install_from_url",
                hash=hash,
                description=f"Installing addon from URL {url}",
                summary={"url": url},
                user=user.name,
                finished=False,
            )

        background_tasks.add_task(
            install_addon_from_url,
            event_id,
            url,
        )
        return InstallAddonResponseModel(event_id=event_id)

    # Store the zip file in a temporary location

    temp_path = f"/tmp/{shortuuid.uuid()}.zip"
    async with aiofiles.open(temp_path, "wb") as f:
        async for chunk in request.stream():
            await f.write(chunk)

    # Get addon name and version from the zip file

    addon_name, addon_version = get_zip_info(temp_path)

    # We don't create the event before we know that the zip file is valid
    # and contains an addon. If it doesn't, an exception is raised before
    # we reach this point.

    # Let's check if we installed this addon before

    query = """
        SELECT id FROM events
        WHERE topic = 'addon.install'
        AND summary->>'addon_name' = $1
        AND summary->>'addon_version' = $2
        LIMIT 1
    """

    res = await Postgres.fetch(query, addon_name, addon_version)
    if res:
        event_id = res[0]["id"]
    else:
        # If not, dispatch a new event
        event_id = await dispatch_event(
            "addon.install",
            description=f"Installing addon {addon_name} {addon_version}",
            summary={
                "addon_name": addon_name,
                "addon_version": addon_version,
                "zip_path": temp_path,
            },
            user=user.name,
            finished=False,
        )

    # Start the installation in the background
    # And return the event ID to the client,
    # so that the client can poll the event status.

    background_tasks.add_task(
        unpack_addon,
        event_id,
        temp_path,
        addon_name,
        addon_version,
    )

    return InstallAddonResponseModel(event_id=event_id)


class AddonInstallListItemModel(OPModel):
    id: str = Field(..., title="Addon ID")
    topic: Literal["addon.install", "addon.install_from_url"] = Field(
        ...,
        title="Event topic",
    )
    description: str = Field(..., title="Addon description")
    addon_name: str = Field(..., title="Addon name")
    addon_version: str = Field(..., title="Addon version")
    user: str | None = Field(None, title="User who installed the addon")
    status: str = Field(..., title="Event status")
    created_at: datetime = Field(..., title="Event creation time")
    updated_at: datetime | None = Field(None, title="Event update time")


class AddonInstallListResponseModel(OPModel):
    items: list[AddonInstallListItemModel] = Field(..., title="List of addons")
    restart_required: bool = Field(...)


@router.get("/install", tags=["Addons"])
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
        summary = row["summary"]
        if last_change is None:
            last_change = row["updated_at"]
        else:
            last_change = max(last_change, row["updated_at"])
        items.append(
            AddonInstallListItemModel(
                id=row["id"],
                topic=row["topic"],
                description=row["description"],
                addon_name=summary["addon_name"],
                addon_version=summary["addon_version"],
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

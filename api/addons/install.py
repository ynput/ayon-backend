import asyncio
import os
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import aiofiles
import shortuuid
from fastapi import BackgroundTasks, Request
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

    addon_name = None
    addon_version = None
    for path in names:
        path = path.strip("/").split("/")
        if len(path) < 2:
            continue
        _name, _version = path[:2]
        if addon_name is None:
            addon_name = _name
            addon_version = _version
            continue
        if _name != addon_name:
            raise RuntimeError("Multiple addon names found in zip file")
        if _version != addon_version:
            raise RuntimeError("Multiple addon versions found in zip file")

    if not (addon_name and addon_version):
        raise RuntimeError("No addon name or version found in zip file")

    return addon_name, addon_version


def unpack_addon_sync(zip_path: str, addon_name: str, addon_version: str):
    logging.info(f"Unpacking addon {addon_name} {addon_version} from {zip_path}")
    target_dir = os.path.join(ayonconfig.addons_dir, addon_name, addon_version)
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)

    # TODO: ensure it works with empty directories, such as private.

    os.makedirs(target_dir)
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        prefix = addon_name + "/" + addon_version + "/"
        for file in zip_ref.namelist():
            if file.startswith(prefix):
                if file.endswith("/"):
                    continue
                else:
                    zip_ref.extract(file, ayonconfig.addons_dir)


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


#
# API
#


class InstallAddonResponseModel(OPModel):
    event_id: str = Field(..., title="Event ID")


@router.post("/install")
async def upload_addon_zip_file(
    user: CurrentUser,
    request: Request,
    background_tasks: BackgroundTasks,
) -> InstallAddonResponseModel:
    """Upload an addon zip file and install it"""

    # Check if the user is allowed to install addons

    if not user.is_admin:
        raise ForbiddenException("Only admins can install addons")

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


class AddonListItemModel(OPModel):
    id: str = Field(..., title="Addon ID")
    description: str = Field(..., title="Addon description")
    addon_name: str = Field(..., title="Addon name")
    addon_version: str = Field(..., title="Addon version")
    user: str | None = Field(None, title="User who installed the addon")
    status: str = Field(..., title="Event status")
    created_at: datetime = Field(..., title="Event creation time")
    updated_at: datetime | None = Field(None, title="Event update time")


@router.get("/install")
def get_installed_addons_list() -> list[AddonListItemModel]:
    """Get a list of installed addons"""

    query = """
        SELECT id, description, summary, user, status, created_at
        FROM events WHERE topic = 'addon.install'
        ORDER BY updated_at DESC
        LIMIT 100
    """

    result = []
    async for row in Postgres.iterate(query):
        summary = row["summary"]
        result.append(
            AddonListItemModel(
                id=row["id"],
                description=row["description"],
                addon_name=summary["addon_name"],
                addon_version=summary["addon_version"],
                user=row["user"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )

    return result


#
# Do wee need this?
#

# class InstallFromUrlRequestModel(OPModel):
#     url: str = Field(..., title="URL to the addon zip file")
#
#
# @router.post("/addons/install/from_url")
# async def install_addon_from_url(
#     user: CurrentUser,
#     request: InstallFromUrlRequestModel,
#     background_tasks: BackgroundTasks,
# ) -> InstallAddonResponseModel:
#     return

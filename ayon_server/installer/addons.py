import asyncio
import json
import os
import shutil
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import aiofiles
import httpx
from nxtools import logging

from ayon_server.config import ayonconfig
from ayon_server.events import update_event


def get_addon_zip_info(path: str) -> tuple[str, str]:
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
    # we do not use download_file() here because using NamedTemporaryFile
    # is much more convenient than manually creating a temporary file

    file_size = 0
    last_time = 0.0

    i = 0
    with tempfile.NamedTemporaryFile(dir=ayonconfig.addons_dir) as temporary_file:
        zip_path = temporary_file.name
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url) as response:
                file_size = int(response.headers.get("content-length", 0))
                async with aiofiles.open(zip_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        await f.write(chunk)
                        i += 1

                        if file_size and (time.time() - last_time > 1):
                            percent = int(i / file_size * 100)
                            await update_event(
                                event_id,
                                progress=int(percent / 2),
                                store=False,
                            )
                            last_time = time.time()

        # Get the addon name and version from the zip file

        addon_name, addon_version = get_addon_zip_info(zip_path)
        await update_event(
            event_id,
            description=f"Installing addon {addon_name} {addon_version}",
            status="in_progress",
            summary={
                "addon_name": addon_name,
                "addon_version": addon_version,
                "url": url,
            },
            progress=50,
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

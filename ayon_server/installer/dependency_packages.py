import os

from ayon_server.events import update_event
from ayon_server.helpers.download import download_file
from ayon_server.installer.common import get_desktop_dir


async def download_dependency_package(event_id: str, url: str):
    target_dir = get_desktop_dir("dependency_packages")
    target_path = os.path.join(target_dir, os.path.basename(url))

    await update_event(event_id, status="in_progress")

    async def on_progress(progress):
        await update_event(event_id, progress=progress, store=False)

    await download_file(url, target_path, progress_handler=on_progress)
    await update_event(event_id, status="finished")

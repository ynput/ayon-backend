import os

from ayon_server.events import update_event
from ayon_server.helpers.download import download_file
from ayon_server.installer.common import get_desktop_dir


async def download_installer(event_id: str, url: str):
    target_dir = get_desktop_dir("installers")
    target_path = os.path.join(target_dir, os.path.basename(url))

    try:
        await download_file(url, target_path)
    except Exception as e:
        print(">>> Download failed", e)
        await update_event(event_id, status="failed", summary={"error": str(e)})

    await update_event(event_id, status="finished")

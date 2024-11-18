from ayon_server.events import EventStream
from ayon_server.helpers.download import download_file
from ayon_server.installer.common import get_desktop_dir


async def download_installer(event_id: str, url: str):
    target_dir = get_desktop_dir("installers")

    await EventStream.update(event_id, status="in_progress")

    async def on_progress(progress):
        await EventStream.update(event_id, progress=progress, store=False)

    await download_file(url, target_dir, progress_handler=on_progress)
    await EventStream.update(event_id, status="finished")

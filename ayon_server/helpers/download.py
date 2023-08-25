import os
import time
import uuid
from typing import Awaitable, Callable

import aiofiles
import httpx

from ayon_server.config import ayonconfig


async def download_file(
    url: str,
    target_path: str,
    filename: str | None = None,
    progress_handler: Callable[[int], Awaitable[None]] | None = None,
) -> None:
    """Downloads a file from a url to a target path"""

    if os.path.isdir(target_path):
        directory = target_path
    else:
        directory = os.path.dirname(target_path)

    if filename is None:
        filename = os.path.basename(url)

    file_size = 0
    last_percent = 0
    last_time = 0.0

    async def handle_progress(i: int) -> None:
        nonlocal file_size
        nonlocal last_percent
        nonlocal last_time

        if progress_handler is None:
            return

        if not file_size:
            return
        percent = i / file_size * 100
        if percent - last_percent < 1:
            return

        if time.time() - last_time < 1:
            return

        last_time = time.time()
        await progress_handler(int(percent))

    target_path = os.path.join(directory, filename)
    temp_file_path = target_path + f".{uuid.uuid1().hex}.part"
    i = 0
    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        async with client.stream("GET", url) as response:
            file_size = int(response.headers.get("content-length", 0))
            directory = os.path.dirname(temp_file_path)
            os.makedirs(directory, exist_ok=True)
            async with aiofiles.open(temp_file_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    await f.write(chunk)
                    i += len(chunk)
                    await handle_progress(i)
    os.rename(temp_file_path, target_path)

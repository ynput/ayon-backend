import os
import time
import uuid
from typing import Awaitable, Callable

import aiofiles
import httpx
from nxtools import log_traceback

from ayon_server.config import ayonconfig
from ayon_server.exceptions import AyonException


def parse_content_disposition(header: str) -> str | None:
    """Parse the Content-Disposition header to extract the filename."""
    parts = header.split(";")
    for part in parts:
        if part.strip().startswith("filename="):
            filename = part.split("=")[1].strip()
            if filename.startswith('"') and filename.endswith('"'):
                filename = filename[1:-1]
            return filename
    return None


async def get_download_file_disposition(url: str) -> dict[str, str | None]:
    """Gets content_length and file_name from a url

    Use HEAD request to retrieve headers, and check for Content-Length
    and Content-Disposition headers.
    If contend-disposition is present, parse attachment line and return filename
    """

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        response = await client.head(url)
        content_length = response.headers.get("content-length")
        file_name = None
        content_disposition = response.headers.get("content-disposition")
        if content_disposition:
            file_name = parse_content_disposition(content_disposition)

        return {"length": content_length, "filename": file_name}


async def download_file(
    url: str,
    target_path: str,
    filename: str | None = None,
    progress_handler: Callable[[int], Awaitable[None]] | None = None,
) -> None:
    """Downloads a file from a url to a target path"""

    if os.path.isdir(target_path):
        directory = target_path
        _filename = None
    else:
        directory, _filename = os.path.split(target_path)

    try:
        disposition = await get_download_file_disposition(url)
        print("Download file disposition", disposition)
    except httpx.HTTPError:
        log_traceback()
        raise AyonException("Failed to get file disposition")

    if filename is None:
        if _filename:
            filename = _filename
        elif disposition.get("filename"):
            filename = disposition["filename"]
        else:
            filename = os.path.basename(url)

    assert filename is not None, "Filename is None. This should not happen"

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

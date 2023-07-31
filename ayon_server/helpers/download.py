import os
import uuid

import aiofiles
import httpx


async def download_file(
    url: str,
    target_path: str,
    filename: str | None = None,
) -> None:
    """Downloads a file from a url to a target path"""

    if os.path.isdir(target_path):
        directory = target_path
    else:
        directory = os.path.dirname(target_path)

    if filename is None:
        filename = os.path.basename(url)

    target_path = os.path.join(directory, filename)
    temp_file_path = target_path + f".{uuid.uuid1().hex}.part"
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url) as response:
            directory = os.path.dirname(temp_file_path)
            os.makedirs(directory, exist_ok=True)
            async with aiofiles.open(temp_file_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    await f.write(chunk)
    os.rename(temp_file_path, target_path)

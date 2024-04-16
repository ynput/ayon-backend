import os

import aiofiles
from fastapi import Request
from starlette.responses import FileResponse

from ayon_server.exceptions import AyonException, BadRequestException, NotFoundException


async def handle_upload(request: Request, target_path: str) -> None:
    """Store raw body from the request to a file."""

    directory, _ = os.path.split(target_path)

    if not os.path.isdir(directory):
        try:
            os.makedirs(directory)
        except Exception as e:
            raise AyonException(f"Failed to create directory: {e}") from e

    i = 0
    async with aiofiles.open(target_path, "wb") as f:
        async for chunk in request.stream():
            await f.write(chunk)
            i += len(chunk)

    if i == 0:
        raise BadRequestException("Empty file")

    return None


async def handle_download(
    path: str,
    media_type: str = "application/octet-stream",
    filename: str | None = None,
) -> FileResponse:
    _, _filename = os.path.split(path)
    if filename is None:
        filename = _filename
    if not os.path.isfile(path):
        raise NotFoundException(f"No such file {filename}")

    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
    )

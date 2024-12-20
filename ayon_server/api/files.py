import os

import aiofiles
from fastapi import Request, Response
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from ayon_server.exceptions import AyonException, BadRequestException, NotFoundException
from ayon_server.helpers.mimetypes import guess_mime_type
from ayon_server.helpers.statistics import update_traffic_stats


async def handle_upload(request: Request, target_path: str) -> int:
    """Store raw body from the request to a file.

    Returns file size in bytes.
    """

    directory, _ = os.path.split(target_path)

    if not os.path.isdir(directory):
        try:
            os.makedirs(directory)
        except Exception as e:
            raise AyonException(f"Failed to create directory: {e}") from e

    i = 0
    try:
        async with aiofiles.open(target_path, "wb") as f:
            async for chunk in request.stream():
                await f.write(chunk)
                i += len(chunk)
    except Exception as e:
        try:
            os.remove(target_path)
        except Exception:
            pass
        raise AyonException(f"Failed to write file: {e}") from e
    finally:
        if i:
            await update_traffic_stats("ingress", i)

    if i == 0:
        try:
            os.remove(target_path)
        except Exception:
            pass
        raise BadRequestException("Empty file")

    return i


async def handle_download(
    path: str,
    media_type: str = "application/octet-stream",
    filename: str | None = None,
    content_disposition_type: str = "attachment",
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
        content_disposition_type=content_disposition_type,
        background=BackgroundTask(
            update_traffic_stats, "egress", os.path.getsize(path)
        ),
    )


def image_response_from_bytes(image_bytes: bytes) -> Response:
    media_type = guess_mime_type(image_bytes)
    if media_type is None:
        raise NotFoundException("Invalid image format")

    return Response(content=image_bytes, media_type=media_type)

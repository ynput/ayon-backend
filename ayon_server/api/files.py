import os

import aiofiles
from fastapi import Request, Response
from starlette.responses import FileResponse

from ayon_server.exceptions import AyonException, BadRequestException, NotFoundException


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
    async with aiofiles.open(target_path, "wb") as f:
        async for chunk in request.stream():
            await f.write(chunk)
            i += len(chunk)

    if i == 0:
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
    )


def guess_mime_type(image_bytes: bytes) -> str | None:
    """Guess the MIME type of an image from its bytes."""
    if image_bytes[0:4] == b"\x89PNG":
        media_type = "image/png"
    elif image_bytes[0:2] == b"\xff\xd8":
        media_type = "image/jpeg"
    elif image_bytes[0:4] == b"<svg":
        media_type = "image/svg+xml"
    elif image_bytes[0:2] == b"BM":
        media_type = "image/bmp"
    elif image_bytes[0:2] == b"II" or image_bytes[0:2] == b"MM":
        media_type = "image/tiff"
    elif image_bytes[0:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        media_type = "image/webp"
    elif image_bytes[0:4] == b"8BPS":
        media_type = "image/vnd.adobe.photoshop"
    elif image_bytes[0:4] == b"GIF8":
        media_type = "image/gif"
    else:
        media_type = None
    return media_type


def image_response_from_bytes(image_bytes: bytes) -> Response:
    media_type = guess_mime_type(image_bytes)
    if media_type is None:
        raise NotFoundException("Invalid image format")

    return Response(content=image_bytes, media_type=media_type)

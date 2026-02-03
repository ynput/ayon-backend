import os
import pathlib
from contextlib import suppress
from typing import Any

import aiofiles
from fastapi import Request, Response
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from ayon_server.exceptions import AyonException, BadRequestException, NotFoundException
from ayon_server.helpers.mimetypes import guess_mime_type
from ayon_server.helpers.statistics import update_traffic_stats


async def handle_upload(
    request: Request,
    target_path: str | pathlib.Path,
    *,
    root_dir: str | pathlib.Path | None = None,
) -> int:
    """Store raw body from the request to a file.

    Important:

    Returns file size in bytes. It is a responsibility of the caller to validate
    whether the file is acceptable and the user has permissions to upload to the
    target path.
    """

    if root_dir is not None:
        root_path = pathlib.Path(root_dir).resolve()
        target_path = (root_path / target_path).resolve()
        if not target_path.is_relative_to(root_path):
            raise NotFoundException("Invalid file path")
    else:
        target_path = pathlib.Path(target_path).resolve()

    directory = target_path.parent

    if not directory.exists():
        try:
            os.makedirs(directory)
        except Exception as e:
            raise AyonException(f"Failed to create directory: {e}") from e

    elif not directory.is_dir():
        raise AyonException("Target directory is not a directory")

    i = 0
    try:
        async with aiofiles.open(target_path, "wb") as f:
            async for chunk in request.stream():
                await f.write(chunk)
                i += len(chunk)

    except Exception as e:
        with suppress(Exception):
            target_path.unlink()
        raise AyonException(f"Failed to write file: {e}") from e

    finally:
        if i:
            await update_traffic_stats("ingress", i)

    if i == 0:
        with suppress(Exception):
            target_path.unlink()
        raise BadRequestException("Empty file")

    return i


async def handle_download(
    path: str | pathlib.Path,
    media_type: str | None = None,
    filename: str | None = None,
    content_disposition_type: str | None = "attachment",
    root_dir: str | pathlib.Path | None = None,
) -> FileResponse:
    """Serve a file from the given path.

    Important: path must be validated before calling this function!
    File existence is checked here, but since we need to be able to serve any file
    and there's no single root directory, we cannot do path validation,
    if only the path is given. It is a responsibility of the caller to ensure
    that the path is safe to serve.

    If `root_dir` is provided, the path is resolved relative to the root and
    validated to be under the root.
    """

    # Normalize the incoming path early
    raw_path = pathlib.Path(path)

    if root_dir is not None:
        # When a root directory is provided, only allow relative paths
        # without any parent-directory traversal components.
        if raw_path.is_absolute() or ".." in raw_path.parts:
            raise NotFoundException("Invalid file path")

        root_path = pathlib.Path(root_dir).resolve()
        requested_path = (root_path / raw_path).resolve()
        if not requested_path.is_relative_to(root_path):
            raise NotFoundException("Invalid file path")
    else:
        requested_path = raw_path.resolve()

    if not requested_path.is_file():
        raise NotFoundException("File not found")

    filename = None
    if content_disposition_type == "attachment":
        filename = requested_path.name if filename is None else filename
    filesize = requested_path.stat().st_size

    kwargs: dict[str, Any] = {}
    if media_type:
        kwargs["media_type"] = media_type
    if content_disposition_type:
        kwargs["content_disposition_type"] = content_disposition_type

    return FileResponse(
        requested_path,
        filename=filename,
        background=BackgroundTask(update_traffic_stats, "egress", filesize),
        **kwargs,
    )


def image_response_from_bytes(image_bytes: bytes) -> Response:
    media_type = guess_mime_type(image_bytes)
    if media_type is None:
        raise NotFoundException("Invalid image format")

    return Response(content=image_bytes, media_type=media_type)

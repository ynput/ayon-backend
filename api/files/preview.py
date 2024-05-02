import os

import aiofiles
from fastapi import Response
from nxtools import logging

from ayon_server.api.files import image_response_from_bytes
from ayon_server.exceptions import NotFoundException, UnsupportedMediaException
from ayon_server.helpers.project_files import id_to_path
from ayon_server.helpers.thumbnails import process_thumbnail
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis

REDIS_NS = "project.file_preview"
FILE_PREVIEW_SIZE = (600, None)

IMAGE_MIME_TYPES = [
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/tiff",
    "image/bmp",
    "image/webp",
    "image/ico",
]


async def obtain_file_preview(project_name: str, file_id: str) -> bytes:
    """Return a preview image for a file as bytes.

    Raises:
        - UnsupportedMediaException if the mimetype is not supported
        for preview generation.
        - NotFoundException if the file or file record is not found.
    """

    path = id_to_path(project_name, file_id)
    if not os.path.isfile(path):
        raise NotFoundException("File not found")

    res = await Postgres.fetch(
        f"""
        SELECT size, data FROM project_{project_name}.files
        WHERE id = $1
        """,
        file_id,
    )

    if not res:
        raise NotFoundException("File record not found")

    file_data = res[0]["data"] or {}
    expected_size = res[0]["size"]
    mime_type = file_data.get("mime", "application/octet-stream")

    if os.path.getsize(path) != expected_size:
        logging.warning(f"File size mismatch: {path}")

    if mime_type in IMAGE_MIME_TYPES:
        async with aiofiles.open(path, "rb") as f:
            image_bytes = await f.read()
            pvw_bytes = await process_thumbnail(image_bytes, FILE_PREVIEW_SIZE)
            return pvw_bytes

    # TODO: return a generic preview image for other file types
    raise UnsupportedMediaException("Preview mode is not supported for this file")


async def get_file_preview(project_name: str, file_id: str) -> Response:
    """Return a preview image for a file.

    Uses the cache if available, otherwise generates a new preview and caches it.
    Returns fastapi.Response object with the image data.
    """
    file_id = file_id.replace("-", "")
    assert len(file_id) == 32

    key = f"{project_name}.{file_id}"
    pvw_bytes = await Redis.get(REDIS_NS, key)

    if pvw_bytes is None:
        pvw_bytes = await obtain_file_preview(project_name, file_id)
        await Redis.set(REDIS_NS, key, pvw_bytes)

    return image_response_from_bytes(pvw_bytes)


async def uncache_file_preview(project_name: str, file_id: str) -> None:
    """Remove the preview image from the cache.

    Silently ignore if the file is not found in the cache.
    """
    file_id = file_id.replace("-", "")
    if len(file_id) != 32:
        raise ValueError("Invalid file ID")
    key = f"{project_name}.{file_id}"
    await Redis.delete(REDIS_NS, key)

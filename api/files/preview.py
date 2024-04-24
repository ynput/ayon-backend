import os

import aiofiles
from fastapi import Response
from nxtools import logging

from ayon_server.api.files import image_response_from_bytes
from ayon_server.exceptions import NotFoundException
from ayon_server.helpers.thumbnails import process_thumbnail
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis

from .common import id_to_path

REDIS_NS = "project.file_preview"
FILE_PREVIEW_SIZE = (600, None)


class UnsupportedPreviewException(Exception):
    pass


async def obtain_file_preview(project_name: str, file_id: str) -> bytes:
    """
    Raises UnsupportedPreviewType if the mimetype is not supported
    for preview generation. That instrucs the caller to serve the
    file directly.
    Returns a tuple of (mime_type, preview_bytes)
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

    if mime_type.startswith("image/"):
        async with aiofiles.open(path, "rb") as f:
            image_bytes = await f.read()
            pvw_bytes = await process_thumbnail(image_bytes, FILE_PREVIEW_SIZE)
            return pvw_bytes

    raise UnsupportedPreviewException("Unsupported preview type")


async def get_file_preview(project_name: str, file_id: str) -> Response:
    file_id = file_id.replace("-", "")
    assert len(file_id) == 32

    key = f"{project_name}.{file_id}"
    pvw_bytes = await Redis.get(REDIS_NS, key)

    if pvw_bytes is None:
        pvw_bytes = await obtain_file_preview(project_name, file_id)
        await Redis.set(REDIS_NS, key, pvw_bytes)
    #     print("Caching preview")
    # else:
    #     print("Using cached preview")

    return image_response_from_bytes(pvw_bytes)


async def uncache_file_preview(project_name: str, file_id: str) -> None:
    file_id = file_id.replace("-", "")
    assert len(file_id) == 32

    key = f"{project_name}.{file_id}"
    await Redis.delete(REDIS_NS, key)

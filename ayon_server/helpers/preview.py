import asyncio
import os

import aiofiles
from fastapi import Response

from ayon_server.api.files import image_response_from_bytes
from ayon_server.config import ayonconfig
from ayon_server.exceptions import (
    AyonException,
    NotFoundException,
    ServiceUnavailableException,
    UnsupportedMediaException,
)
from ayon_server.files import Storages
from ayon_server.helpers.mimetypes import is_image_mime_type, is_video_mime_type
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import log_traceback, logger
from ayon_server.utils.request_coalescer import RequestCoalescer

REDIS_NS = "project.file_preview"
PREVIEW_CACHE_TTL = 3600 * 4
PREVIEW_SEMAPHORE = asyncio.Semaphore(3)


async def create_video_thumbnail(
    video_path: str,
    *,
    timestamp: float | None = None,
    thumbnail: bool = True,
) -> bytes:
    """Create a thumbnail image for a video file.

    Returns the thumbnail image as bytes.
    """

    async with PREVIEW_SEMAPHORE:
        async with aiofiles.tempfile.NamedTemporaryFile(
            suffix=".jpg", delete=True
        ) as temp_file:
            temp_path = str(temp_file.name)

            cmd: list[str] = ["ffmpeg", "-hide_banner", "-loglevel", "error"]

            if timestamp is not None:
                cmd.extend(["-ss", str(timestamp)])

            cmd.extend(["-y", "-i", video_path])
            if thumbnail:
                target_size = ayonconfig.thumbnail_size
                cmd.extend(
                    [
                        "-filter:v",
                        f"scale={target_size}:-1",
                    ]
                )

            cmd.extend(
                [
                    "-frames:v",
                    "1",
                    "-c:v",
                    "mjpeg",
                    temp_path,
                ]
            )

            safe_file_name = video_path.split("?")[0]
            logger.trace(f"Extracting still from {safe_file_name}")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                _, stderr = await proc.communicate()
            except asyncio.CancelledError:
                logger.warning("Thumbnail generation cancelled. Terminating ffmpeg.")
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except Exception:
                    proc.kill()
                raise

            if proc.returncode != 0:
                stderr_str = stderr.decode()
                logger.error(f"ffmpeg failed: {stderr_str}")
                return b""

            async with aiofiles.open(temp_path, "rb") as f:
                image_bytes = await f.read()

        return image_bytes


async def obtain_file_preview(
    project_name: str,
    file_id: str,
    thumbnail: bool = True,
) -> bytes:
    """Return a preview image for a file as bytes.


    Raises:
        - UnsupportedMediaException if the mimetype is not supported
        for preview generation.
        - NotFoundException if the file or file record is not found.
    """
    logger.trace(f"Retrieving file preview {project_name}/{file_id}")

    res = await Postgres.fetch(
        f"""
        SELECT size, data FROM project_{project_name}.files
        WHERE id = $1
        """,
        file_id,
    )

    if not res:
        raise NotFoundException("File record not found")
    file_record = res[0]
    file_data = file_record["data"] or {}
    expected_size = res[0]["size"]
    mime_type = file_data.get("mime", "application/octet-stream")

    # Get the file location

    storage = await Storages.project(project_name)

    if storage.storage_type == "local":
        path = await storage.get_path(file_id)

        if not os.path.isfile(path):
            raise NotFoundException(
                f"Cannot obtain file {project_name}/{file_id} preview: media not found"
            )

        if os.path.getsize(path) != expected_size:
            logger.warning(f"File size mismatch for {project_name}/{file_id}")

    elif storage.storage_type == "s3":
        path = await storage.get_signed_url(file_id)

    else:
        raise AyonException("Unsupported storage type. This should not happen")

    if is_video_mime_type(mime_type) or is_image_mime_type(mime_type):
        pvw_bytes = await create_video_thumbnail(path, thumbnail=thumbnail)
        return pvw_bytes

    raise UnsupportedMediaException(
        f"Preview mode is not supported for {mime_type} files "
        f"({project_name}/{file_id})"
    )


async def get_file_preview_bytes(
    project_name: str,
    file_id: str,
    retries: int = 0,
) -> bytes:
    """Return a preview image for a file.

    Uses the cache if available, otherwise generates a new preview and caches it.
    Returns fastapi.Response object with the image data.
    """

    file_id = file_id.replace("-", "")
    assert len(file_id) == 32

    key = f"{project_name}.{file_id}"
    pvw_bytes = await Redis.get(REDIS_NS, key)

    if pvw_bytes is None:
        try:
            pvw_bytes = await obtain_file_preview(project_name, file_id)
            await Redis.set(REDIS_NS, key, pvw_bytes, ttl=PREVIEW_CACHE_TTL)
        except ServiceUnavailableException:
            await asyncio.sleep(0.2)
            if retries < 3:
                return await get_file_preview_bytes(project_name, file_id, retries + 1)
            raise ServiceUnavailableException("File preview service unavailable")
    elif pvw_bytes != b"":
        # Bump the TTL only for successful cached previews.
        # Negative cache entries should expire naturally so transient
        # preview-generation/storage failures can recover automatically.
        await Redis.expire(REDIS_NS, key, PREVIEW_CACHE_TTL)

    if pvw_bytes == b"":
        raise NotFoundException("File preview not available")
    return pvw_bytes


async def get_file_preview(
    project_name: str,
    file_id: str,
    retries: int = 0,
) -> Response:
    coalesce = RequestCoalescer()
    try:
        pvw_bytes = await coalesce(
            get_file_preview_bytes,
            project_name,
            file_id,
            retries,
        )
    except NotFoundException:
        raise
    except UnsupportedMediaException:
        raise
    except Exception as e:
        log_traceback("Error getting file preview")
        raise AyonException(f"Error getting file preview: {str(e)}") from e
    return image_response_from_bytes(pvw_bytes, headers={"X-File-ID": file_id})


async def uncache_file_preview(project_name: str, file_id: str) -> None:
    """Remove the preview image from the cache.

    Silently ignore if the file is not found in the cache.
    """
    file_id = file_id.replace("-", "")
    if len(file_id) != 32:
        raise ValueError("Invalid file ID")
    key = f"{project_name}.{file_id}"
    await Redis.delete(REDIS_NS, key)

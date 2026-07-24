import asyncio
import os

import aiofiles
from fastapi import Response

from ayon_server.api.files import image_response_from_bytes
from ayon_server.config import ayonconfig
from ayon_server.entities import (
    FolderEntity,
    TaskEntity,
    UserEntity,
    VersionEntity,
    WorkfileEntity,
)
from ayon_server.exceptions import (
    AyonException,
    NotFoundException,
    ServiceUnavailableException,
    UnsupportedMediaException,
)
from ayon_server.files import Storages
from ayon_server.helpers.mimetypes import is_image_mime_type, is_video_mime_type
from ayon_server.helpers.thumbnails.common import get_fake_thumbnail, retrieve_thumbnail
from ayon_server.helpers.thumbnails.store_thumbnail import store_thumbnail
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.utils.hashing import create_uuid
from ayon_server.utils.request_coalescer import RequestCoalescer

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
                raise AyonException(f"FFMPeg failed: {stderr_str}")

            async with aiofiles.open(temp_path, "rb") as f:
                image_bytes = await f.read()

        return image_bytes


async def obtain_file_preview(
    project_name: str,
    file_id: str,
    *,
    thumbnail: bool = True,
    user: str | UserEntity | None = None,
    thumbnail_id: str | None = None,
    for_entity: FolderEntity
    | TaskEntity
    | VersionEntity
    | WorkfileEntity
    | None = None,
) -> bytes:
    """Return a preview image for a file as bytes.


    Raises:
        - UnsupportedMediaException if the mimetype is not supported
        for preview generation.
        - NotFoundException if the file or file record is not found.
    """
    logger.trace(f"Retrieving file preview {project_name}/{file_id}")

    file_record = await Postgres.fetchrow(
        f"""
        SELECT size, data, thumbnail_id FROM project_{project_name}.files
        WHERE id = $1
        """,
        file_id,
    )

    if not file_record:
        raise NotFoundException("File record not found")

    if file_record["thumbnail_id"]:
        existing_thumbnail_id = file_record["thumbnail_id"]
        thumb_bytes = await retrieve_thumbnail(
            project_name=project_name,
            thumbnail_id=existing_thumbnail_id,
            mode="small" if thumbnail else "original",
        )
        if thumb_bytes:
            if for_entity and for_entity.thumbnail_id != existing_thumbnail_id:
                for_entity.thumbnail_id = existing_thumbnail_id
                await for_entity.save()
            return thumb_bytes
    file_data = file_record["data"] or {}
    expected_size = file_record["size"]
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
        try:
            pvw_bytes = await create_video_thumbnail(path, thumbnail=thumbnail)
        except Exception as e:
            logger.error(
                f"Error creating preview for {project_name}/{file_id}: {str(e)}"
            )
            pvw_bytes = get_fake_thumbnail()

        if thumbnail_id is None:
            thumbnail_id = create_uuid()

        user_name = user.name if isinstance(user, UserEntity) else user

        await store_thumbnail(
            project_name=project_name,
            thumbnail_id=thumbnail_id,
            payload=pvw_bytes,
            mime="image/jpeg",
            user_name=user_name,
            entity=for_entity,
        )
        await Postgres.execute(
            f"""
            UPDATE project_{project_name}.files
            SET updated_at = NOW(), thumbnail_id = $2
            WHERE id = $1
            """,
            file_id,
            thumbnail_id,
        )
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
    """Return a preview image for a file."""

    file_id = file_id.replace("-", "")
    assert len(file_id) == 32

    try:
        return await obtain_file_preview(project_name, file_id)
    except ServiceUnavailableException:
        await asyncio.sleep(0.2)
        if retries < 3:
            return await get_file_preview_bytes(project_name, file_id, retries + 1)
        raise ServiceUnavailableException("File preview service unavailable")


async def get_file_preview_response(
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

    except Exception as e:
        logger.error(f"Error getting file {project_name}/{file_id} thumbnail: {str(e)}")
        raise AyonException(f"Error getting file preview: {str(e)}") from e
    return image_response_from_bytes(pvw_bytes, headers={"X-File-ID": file_id})

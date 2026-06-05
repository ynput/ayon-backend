import uuid

from ayon_server.exceptions import UnsupportedMediaException
from ayon_server.files import Storages
from ayon_server.helpers.mimetypes import guess_mime_type
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger

from .process_thumbnail import (
    MAX_THUMBNAIL_HEIGHT,
    MAX_THUMBNAIL_WIDTH,
    ThumbnailProcessNoop,
    process_thumbnail,
)


async def store_thumbnail(
    project_name: str,
    thumbnail_id: str,
    payload: bytes,
    *,
    mime: str | None = None,
    user_name: str | None = None,
):
    """Store a thumbnail in the database and the storage service."""
    if len(payload) < 10:
        raise UnsupportedMediaException("Thumbnail cannot be empty")

    logger.trace(f"Storing thumbnail {project_name}/{thumbnail_id}")

    guessed_mime = guess_mime_type(payload)
    if guessed_mime is None:
        # This shouldn't happen, but we'll log it.
        # Upload will probably fail later on, in process_thumbnail.
        logger.warning(f"Could not guess mime type of thumbnail. Using provided {mime}")

    elif mime and guessed_mime != mime:
        # This is a warning, not an error, because we can still store the thumbnail
        # even if the mime type is wrong. We're just logging it and using the
        # correct mime type instead of the provided one.
        logger.warning(
            "Thumbnail mime type mismatch: "
            f"Payload contains {guessed_mime} "
            f"but was requested to store {mime}"
        )
        mime = guessed_mime

    if mime not in ["image/png", "image/jpeg"]:
        raise UnsupportedMediaException(f"Unsupported thumbnail mime type {mime}")

    try:
        thumbnail = await process_thumbnail(
            payload,
            (MAX_THUMBNAIL_WIDTH, MAX_THUMBNAIL_HEIGHT),
            raise_on_noop=True,
        )
    except ValueError as e:
        raise UnsupportedMediaException(str(e))

    except ThumbnailProcessNoop:
        thumbnail = payload
    else:
        storage = await Storages.project(project_name)
        await storage.store_thumbnail(thumbnail_id, payload)

    meta = {
        "originalSize": len(payload),
        "thumbnailSize": len(thumbnail),
        "mime": mime,  # eventually, we'll drop the column
    }
    if user_name:
        meta["author"] = user_name

    query = f"""
        INSERT INTO project_{project_name}.thumbnails (id, mime, data, meta)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (id)
        DO UPDATE SET
            data = EXCLUDED.data,
            mime = EXCLUDED.mime,
            meta = EXCLUDED.meta
    """
    await Postgres.execute(query, thumbnail_id, mime, thumbnail, meta)

    thumbnail_hash = uuid.uuid4().hex[:6]
    for entity_type in ["workfiles", "versions", "folders", "tasks"]:
        await Postgres.execute(
            f"""
            UPDATE project_{project_name}.{entity_type}
            SET updated_at = NOW(),
            data = data || $2
            WHERE thumbnail_id = $1
            """,
            thumbnail_id,
            {"thumbnailHash": thumbnail_hash},
        )

    await Redis.delete("thumbnail", f"{project_name}:{thumbnail_id}:small")
    await Redis.delete("thumbnail", f"{project_name}:{thumbnail_id}:original")


async def store_project_skeleton_thumbnail(
    project_name: str,
    payload,
    *,
    mime: str | None = None,
    user_name: str | None = None,
):
    """Store a thumbnail for the project skeleton."""
    if len(payload) < 10:
        raise UnsupportedMediaException("Thumbnail cannot be empty")

    guessed_mime = guess_mime_type(payload)
    if guessed_mime is None:
        # This shouldn't happen, but we'll log it.
        # Upload will probably fail later on, in process_thumbnail.
        logger.warning(f"Could not guess mime type of thumbnail. Using provided {mime}")

    elif mime is None:
        mime = guessed_mime

    elif guessed_mime != mime:
        # This is a warning, not an error, because we can still store the thumbnail
        # even if the mime type is wrong. We're just logging it and using the
        # correct mime type instead of the provided one.
        logger.warning(
            "Thumbnail mime type mismatch: "
            f"Payload contains {guessed_mime} "
            f"but was requested to store {mime}"
        )
        mime = guessed_mime

    if mime not in ["image/png", "image/jpeg"]:
        raise UnsupportedMediaException(f"Unsupported thumbnail mime type {mime}")

    try:
        thumbnail = await process_thumbnail(
            payload,
            (MAX_THUMBNAIL_WIDTH, MAX_THUMBNAIL_HEIGHT),
            raise_on_noop=True,
        )
    except ValueError as e:
        raise UnsupportedMediaException(str(e))

    except ThumbnailProcessNoop:
        thumbnail = payload

    meta = {
        "originalSize": len(payload),
        "thumbnailSize": len(thumbnail),
        "mime": mime,  # eventually, we'll drop the column
    }
    if user_name:
        meta["author"] = user_name

    query = """
        INSERT INTO public.project_skeleton_thumbnails
        (project_name, mime, data, meta)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (project_name)
        DO UPDATE SET
            data = EXCLUDED.data,
            mime = EXCLUDED.mime,
            meta = EXCLUDED.meta
    """
    await Postgres.execute(query, project_name, mime, thumbnail, meta)

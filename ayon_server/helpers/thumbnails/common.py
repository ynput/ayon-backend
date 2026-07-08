import base64
import functools
from typing import Literal, NotRequired, TypedDict

from fastapi import Response

from ayon_server.exceptions import NotFoundException
from ayon_server.files import Storages
from ayon_server.helpers.mimetypes import guess_mime_type
from ayon_server.helpers.preview import get_file_preview_bytes
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.utils.request_coalescer import RequestCoalescer

PlaceholderOption = Literal["empty", "none"]


@functools.cache
def get_fake_thumbnail() -> bytes:
    """Returns a fake thumbnail image as a byte stream.

    The image is a 1x1 pixel PNG.
    """
    base64_string = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="  # noqa
    return base64.b64decode(base64_string)


class ThumbnailInfo(TypedDict):
    project_name: str
    path: str
    thumbnail_id: NotRequired[str | None]
    file_id: NotRequired[str | None]


class ThumbnailData(TypedDict):
    content: bytes | None
    mime: str


@Redis.cached(
    "thumbnail",
    "{project_name}:{thumbnail_id}:{mode}",
    ttl=300,
    model="bytes",
)
async def retrieve_thumbnail(
    project_name: str,
    thumbnail_id: str,
    mode: Literal["small", "original"] = "small",
) -> bytes | None:
    logger.trace(f"Retrieving thumbnail {project_name}/{thumbnail_id}")
    content = None
    query = f"""
        SELECT data, mime, created_at
        FROM project_{project_name}.thumbnails
        WHERE id = $1
    """
    row = await Postgres.fetchrow(query, thumbnail_id)
    if row:
        content = row["data"]
    if mode == "original":
        storage = await Storages.project(project_name)
        try:
            content = await storage.get_thumbnail(thumbnail_id)
        except FileNotFoundError:
            pass
    return content


async def get_thumbnail_response(
    thumbnail_info: ThumbnailInfo,
    *,
    placeholder_option: PlaceholderOption = "none",
    original: bool = False,
) -> Response:
    coalesce = RequestCoalescer()
    thumbnail_id = thumbnail_info.get("thumbnail_id")
    file_id = thumbnail_info.get("file_id")

    content = None
    headers = {"Cache-Control": "public, max-age=31536000, immutable"}

    if thumbnail_id:
        content = await coalesce(
            retrieve_thumbnail,
            thumbnail_info["project_name"],
            thumbnail_id,
            "original" if original else "small",
        )
        headers["X-Thumbnail-Id"] = thumbnail_id

    elif file_id:
        try:
            content = await coalesce(
                get_file_preview_bytes,
                thumbnail_info["project_name"],
                file_id,
            )
            headers["X-File-Id"] = file_id
        except NotFoundException:
            # Missing preview is expected for some files.
            # Leave `content` as None and let the fallback logic below decide
            # whether to return a placeholder or raise NotFoundException.
            pass

    # Construct the response. If nothing is found,
    # either return a fake thumbnail or raise an exception based
    # on the placeholder_option.

    if content is None:
        if placeholder_option == "empty":
            content = get_fake_thumbnail()
            headers["Cache-Control"] = (
                "public, max-age=3600"  # Cache the empty thumbnail for a shorter time
            )
            mime = "image/png"
        else:
            raise NotFoundException("No thumbnail available")
    else:
        mime = guess_mime_type(content) or "image/png"

    return Response(
        content=content,
        media_type=mime,
        headers=headers,
    )

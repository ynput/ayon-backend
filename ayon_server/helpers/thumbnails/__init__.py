__all__ = [
    "get_fake_thumbnail",
    "store_thumbnail",
    "store_project_skeleton_thumbnail",
    "process_thumbnail",
    "calculate_scaled_size",
    "ThumbnailProcessNoop",
    "PlaceholderOption",
]

from fastapi import Response

from ayon_server.entities import UserEntity
from ayon_server.utils.request_coalescer import RequestCoalescer

from .common import (
    PlaceholderOption,
    get_fake_thumbnail,
    get_thumbnail_response,
)
from .process_thumbnail import (
    ThumbnailProcessNoop,
    calculate_scaled_size,
    process_thumbnail,
)
from .store_thumbnail import store_project_skeleton_thumbnail, store_thumbnail
from .thumbnail_acl import ensure_accessible
from .thumbnail_info_resolvers import (
    resolve_folder_thumbnail_info,
    resolve_task_thumbnail_info,
    resolve_version_thumbnail_info,
)


async def resolve_thumbnail(
    project_name: str,
    entity_type: str,
    entity_id: str,
    *,
    user: UserEntity,
    placeholder: PlaceholderOption = "none",
    original: bool = False,
) -> Response:
    coalesce = RequestCoalescer()

    if entity_type == "folder":
        resolver = resolve_folder_thumbnail_info
    elif entity_type == "task":
        resolver = resolve_task_thumbnail_info
    elif entity_type == "version":
        resolver = resolve_version_thumbnail_info
    elif entity_type == "workfile":
        from .thumbnail_info_resolvers import resolve_workfile_thumbnail_info

        resolver = resolve_workfile_thumbnail_info
    else:
        raise ValueError(f"Unsupported entity type '{entity_type}' for thumbnail")

    thumbnail_info = await coalesce(
        resolver,
        project_name,
        entity_id,
    )
    await ensure_accessible(thumbnail_info, user)

    return await get_thumbnail_response(
        thumbnail_info,
        placeholder_option=placeholder or "none",
        original=original,
    )

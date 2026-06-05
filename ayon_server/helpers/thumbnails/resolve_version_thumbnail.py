from fastapi import Response

from ayon_server.entities import UserEntity
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.utils.request_coalescer import RequestCoalescer

from .common import PlaceholderOption, ThumbnailInfo, get_thumbnail_response
from .thumbnail_acl import ensure_accessible


@Redis.cached("thumbnail-info", "{project_name}:{version_id}", ttl=600)
async def get_thumbnail_info_for_version(
    project_name: str,
    version_id: str,
) -> ThumbnailInfo:
    query = f"""
        WITH reviewables AS (
            SELECT DISTINCT ON (a.entity_id)
            a.entity_id AS version_id,
            f.id AS reviewable_id
            FROM project_{project_name}.files f
            JOIN project_{project_name}.activity_feed a
            ON a.activity_id = f.activity_id
            AND a.entity_type = 'version'
            AND a.activity_type = 'reviewable'
            AND a.reference_type = 'origin'
            ORDER BY a.entity_id, a.created_at DESC
        )
        SELECT
            h.path,
            v.thumbnail_id,
            r.reviewable_id
        FROM project_{project_name}.versions v

        JOIN project_{project_name}.products p
        ON p.id = v.product_id

        JOIN project_{project_name}.hierarchy h
        ON h.id = p.folder_id

        LEFT JOIN reviewables r
        ON r.version_id = v.id

        WHERE v.id = $1
    """

    res = await Postgres.fetchrow(query, version_id)
    if not res:
        raise NotFoundException("Version not found")

    return {
        "project_name": project_name,
        "path": res["path"],
        "thumbnail_id": res["thumbnail_id"],
        "file_id": res["reviewable_id"],
    }


async def resolve_version_thumbnail(
    project_name: str,
    version_id: str,
    *,
    user: UserEntity,
    placeholder: PlaceholderOption = "none",
    original: bool = False,
) -> Response:
    coalesce = RequestCoalescer()

    thumbnail_info = await coalesce(
        get_thumbnail_info_for_version,
        project_name,
        version_id,
    )

    await ensure_accessible(thumbnail_info, user)

    return await get_thumbnail_response(
        thumbnail_info,
        placeholder_option=placeholder or "none",
        original=original,
    )

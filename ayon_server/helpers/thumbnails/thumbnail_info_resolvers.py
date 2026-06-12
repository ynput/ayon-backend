from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis

from .common import ThumbnailInfo

THUMBNAIL_INFO_TTL = 600  # 10 minutes


@Redis.cached("thumbnail-info", "{project_name}:{entity_id}", ttl=THUMBNAIL_INFO_TTL)
async def resolve_folder_thumbnail_info(
    project_name: str,
    entity_id: str,
) -> ThumbnailInfo:
    query = f"""
        WITH reviewables AS (
                SELECT DISTINCT ON (f.id)
                p.folder_id AS folder_id,
                f.id AS reviewable_id,
                a.created_at AS reviewable_created_at,
                v.thumbnail_id AS version_thumbnail_id
            FROM project_{project_name}.folders entity
            JOIN project_{project_name}.products p
                ON p.folder_id = entity.id
            JOIN project_{project_name}.versions v
                ON v.product_id = p.id
            JOIN project_{project_name}.activity_feed a
                ON a.entity_id = v.id
                AND a.entity_type = 'version'
                AND a.activity_type = 'reviewable'
                AND a.reference_type = 'origin'
            JOIN project_{project_name}.files f
                ON f.activity_id = a.activity_id
            WHERE entity.id = $1
            ORDER BY f.id, a.created_at DESC
        )
        SELECT
            r.reviewable_id AS reviewable_id,
            r.version_thumbnail_id AS version_thumbnail_id,
            entity.thumbnail_id AS thumbnail_id,
            hierarchy.path AS path
        FROM project_{project_name}.folders entity
        INNER JOIN project_{project_name}.hierarchy AS hierarchy
            ON entity.id = hierarchy.id
        LEFT JOIN reviewables r
            ON r.folder_id = entity.id
        WHERE entity.id = $1
        ORDER BY r.reviewable_created_at DESC LIMIT 1;
    """

    res = await Postgres.fetchrow(query, entity_id)
    if not res:
        raise NotFoundException("Folder not found")

    return {
        "project_name": project_name,
        "path": res["path"],
        "thumbnail_id": res["thumbnail_id"] or res["version_thumbnail_id"],
        "file_id": res["reviewable_id"],
    }


@Redis.cached("thumbnail-info", "{project_name}:{entity_id}", ttl=THUMBNAIL_INFO_TTL)
async def resolve_task_thumbnail_info(
    project_name: str,
    entity_id: str,
) -> ThumbnailInfo:

    query = f"""
        WITH reviewables AS (
            SELECT DISTINCT ON (v.id)
                v.task_id AS task_id,
                v.thumbnail_id AS version_thumbnail_id,
                f.id AS reviewable_id,
                a.created_at AS reviewable_created_at
            FROM project_{project_name}.tasks entity
            JOIN project_{project_name}.versions v
                ON v.task_id = entity.id
            JOIN project_{project_name}.activity_feed a
                ON a.entity_id = v.id
                AND a.entity_type = 'version'
                AND a.activity_type = 'reviewable'
                AND a.reference_type = 'origin'
            JOIN project_{project_name}.files f
                ON f.activity_id = a.activity_id
            WHERE entity.id = $1
            ORDER BY v.id, a.created_at DESC
        )
        SELECT
            entity.thumbnail_id AS thumbnail_id,
            r.reviewable_id AS reviewable_id,
            r.version_thumbnail_id AS version_thumbnail_id,
            hierarchy.path AS folder_path
        FROM project_{project_name}.tasks entity

        JOIN project_{project_name}.hierarchy AS hierarchy
            ON entity.folder_id = hierarchy.id

        LEFT JOIN reviewables r
            ON r.task_id = entity.id
        WHERE entity.id = $1
        ORDER BY r.reviewable_created_at DESC LIMIT 1;
    """

    res = await Postgres.fetchrow(query, entity_id)
    if not res:
        raise NotFoundException("Task not found")

    return {
        "project_name": project_name,
        "path": res["folder_path"],
        "thumbnail_id": res["thumbnail_id"] or res["version_thumbnail_id"],
        "file_id": res["reviewable_id"],
    }


@Redis.cached("thumbnail-info", "{project_name}:{entity_id}", ttl=THUMBNAIL_INFO_TTL)
async def resolve_version_thumbnail_info(
    project_name: str,
    entity_id: str,
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

    res = await Postgres.fetchrow(query, entity_id)
    if not res:
        raise NotFoundException("Version not found")

    return {
        "project_name": project_name,
        "path": res["path"],
        "thumbnail_id": res["thumbnail_id"],
        "file_id": res["reviewable_id"],
    }


@Redis.cached("thumbnail-info", "{project_name}:{entity_id}", ttl=THUMBNAIL_INFO_TTL)
async def resolve_workfile_thumbnail_info(
    project_name: str,
    entity_id: str,
) -> ThumbnailInfo:
    query = f"""
        SELECT
            w.thumbnail_id AS thumbnail_id,
            h.path AS path
        FROM project_{project_name}.workfiles w
        JOIN project_{project_name}.hierarchy h
        ON w.folder_id = h.id
        WHERE w.id = $1
    """

    res = await Postgres.fetchrow(query, entity_id)
    if not res:
        raise NotFoundException("Workfile not found")

    return {
        "project_name": project_name,
        "path": res["path"],
        "thumbnail_id": res["thumbnail_id"],
        "file_id": None,
    }

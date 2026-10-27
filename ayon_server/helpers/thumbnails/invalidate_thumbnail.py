import uuid
from typing import Any

from ayon_server.events.eventstream import EventStream
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import OPModel


class AffectedEntity(OPModel):
    entity_type: str
    entity_id: str
    thumbnail_hash: str
    thumbnail_id: str | None = None


def thumbnail_updated_event(
    project_name: str,
    affected_entity: AffectedEntity,
) -> dict[str, Any]:
    """Build kwargs for a (non-stored) `thumbnail.updated` event."""
    return {
        "topic": "thumbnail.updated",
        "project": project_name,
        "description": "Thumbnail updated",
        "summary": {
            "entityType": affected_entity.entity_type,
            "entityId": affected_entity.entity_id,
            "thumbnailHash": affected_entity.thumbnail_hash,
        },
        "store": False,
    }


async def invalidate_version_parents_thumbnails(
    project_name: str,
    version_ids: list[str],
) -> list[AffectedEntity]:
    """Invalidate thumbnails of folders and tasks of the given versions.

    Folder and task thumbnails may be inherited from their versions, so when
    a version thumbnail changes, parent thumbnail hashes must be bumped and
    their cached thumbnail info dropped.

    This is done using a single query. Events are NOT dispatched here,
    callers are responsible for dispatching `thumbnail.updated` events
    (see `thumbnail_updated_event`), as they may need to defer them
    until the transaction is committed.
    """
    if not version_ids:
        return []

    query = f"""
        WITH parents AS (
            SELECT p.folder_id, v.task_id
            FROM project_{project_name}.versions v
            JOIN project_{project_name}.products p ON p.id = v.product_id
            WHERE v.id = ANY($1::uuid[])
        ),
        updated_folders AS (
            UPDATE project_{project_name}.folders
            SET
                updated_at = NOW(),
                data = data || jsonb_build_object(
                    'thumbnailHash', substr(md5(random()::text), 1, 6)
                )
            WHERE id IN (SELECT folder_id FROM parents)
            RETURNING 'folder' AS entity_type, id, data->>'thumbnailHash' AS hash
        ),
        updated_tasks AS (
            UPDATE project_{project_name}.tasks
            SET
                updated_at = NOW(),
                data = data || jsonb_build_object(
                    'thumbnailHash', substr(md5(random()::text), 1, 6)
                )
            WHERE id IN (SELECT task_id FROM parents WHERE task_id IS NOT NULL)
            RETURNING 'task' AS entity_type, id, data->>'thumbnailHash' AS hash
        )
        SELECT entity_type, id, hash FROM updated_folders
        UNION ALL
        SELECT entity_type, id, hash FROM updated_tasks
    """

    affected_entities: list[AffectedEntity] = []
    for row in await Postgres.fetch(query, version_ids):
        entity_id = row["id"]
        await Redis.delete("thumbnail-info", f"{project_name}:{entity_id}")
        affected_entities.append(
            AffectedEntity(
                entity_type=row["entity_type"],
                entity_id=entity_id,
                thumbnail_hash=row["hash"],
            )
        )
    return affected_entities


async def invalidate_thumbnail_by_entity(
    project_name: str,
    entity_type: str,
    entity_id: str,
) -> list[AffectedEntity]:
    """Invalidate thumbnail by entity id."""

    thumbnail_hash = uuid.uuid4().hex[:6]

    affected_entities = [
        AffectedEntity(
            entity_type=entity_type,
            entity_id=entity_id,
            thumbnail_hash=thumbnail_hash,
        )
    ]

    logger.trace(f"Invalidating thumbnail for {project_name} {entity_type} {entity_id}")

    await Redis.delete("thumbnail-info", f"{project_name}:{entity_id}")
    await Postgres.execute(
        f"""
        UPDATE project_{project_name}.{entity_type}s
        SET updated_at = NOW(), data = data || $2
        WHERE id = $1
        """,
        entity_id,
        {"thumbnailHash": thumbnail_hash},
    )

    if entity_type == "version":
        # also invalidate folder and task thumbnail
        parents = await invalidate_version_parents_thumbnails(project_name, [entity_id])
        for parent in parents:
            await EventStream.dispatch(**thumbnail_updated_event(project_name, parent))
        affected_entities.extend(parents)

    await EventStream.dispatch(
        "thumbnail.updated",
        project=project_name,
        description="Thumbnail updated",
        summary={
            "entityType": entity_type,
            "entityId": entity_id,
            "thumbnailHash": thumbnail_hash,
        },
        store=False,
    )
    return affected_entities


async def invalidate_thumbnail_by_id(
    project_name: str,
    thumbnail_id: str,
) -> list[AffectedEntity]:
    """Invalidate thumbnail by thumbnail id.

    This function is called when a thumbnail is uploaded or deleted.
    It updates the thumbnail hash on affected entities and deletes
    the thumbnail from the cache.
    """

    await Redis.delete("thumbnail", f"{project_name}:{thumbnail_id}:small")
    await Redis.delete("thumbnail", f"{project_name}:{thumbnail_id}:original")

    affected_entities: list[AffectedEntity] = []

    async with Postgres.transaction():
        for entity_type in ["workfile", "version", "folder", "task"]:
            res = await Postgres.fetch(
                f"""
                SELECT id FROM project_{project_name}.{entity_type}s
                WHERE thumbnail_id = $1
                """,
                thumbnail_id,
            )

            for row in res:
                affected_entities.extend(
                    await invalidate_thumbnail_by_entity(
                        project_name,
                        entity_type,
                        row["id"],
                    )
                )
    return affected_entities

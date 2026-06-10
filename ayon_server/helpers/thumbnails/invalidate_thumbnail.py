import uuid

from ayon_server.events.eventstream import EventStream
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import OPModel


class AffectedEntity(OPModel):
    entity_type: str
    entity_id: str
    thumbnail_hash: str


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
            thumbnail_hash=uuid.uuid4().hex[:6],
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
        res = await Postgres.fetchrow(
            f"""
            SELECT
                products.folder_id,
                tasks.id AS task_id
            FROM project_{project_name}.products
            JOIN project_{project_name}.versions
                ON versions.product_id = products.id
            LEFT JOIN project_{project_name}.tasks
                ON tasks.id = versions.task_id
            WHERE versions.id = $1
            """,
            entity_id,
        )
        if res:
            if res["folder_id"]:
                affected_entities.extend(
                    await invalidate_thumbnail_by_entity(
                        project_name,
                        "folder",
                        res["folder_id"],
                    )
                )
            if res["task_id"]:
                affected_entities.extend(
                    await invalidate_thumbnail_by_entity(
                        project_name,
                        "task",
                        res["task_id"],
                    )
                )

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

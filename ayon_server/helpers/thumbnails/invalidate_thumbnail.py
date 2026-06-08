import uuid

from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis


async def invalidate_thumbnail_by_entity(project_name: str, entity_id: str) -> None:
    """Invalidate thumbnail by entity id."""
    pass


async def invalidate_thumbnail_by_id(project_name: str, thumbnail_id: str) -> None:
    """Invalidate thumbnail by thumbnail id.

    This function is called when a thumbnail is uploaded or deleted.
    It updates the thumbnail hash on affected entities and deletes
    the thumbnail from the cache.
    """

    thumbnail_hash = uuid.uuid4().hex[:6]

    async with Postgres.transaction():
        for entity_type in ["workfiles", "versions", "folders", "tasks"]:
            await Postgres.execute(
                f"""
                UPDATE project_{project_name}.{entity_type}
                SET
                    updated_at = NOW(),
                    data = data || $2
                WHERE
                    thumbnail_id = $1
                """,
                thumbnail_id,
                {"thumbnailHash": thumbnail_hash},
            )

            # TODO: bump hash on entities that use the thumbnail as fallback

    await Redis.delete("thumbnail", f"{project_name}:{thumbnail_id}:small")
    await Redis.delete("thumbnail", f"{project_name}:{thumbnail_id}:original")

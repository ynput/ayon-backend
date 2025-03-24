from ayon_server.entities import UserEntity
from ayon_server.entity_lists.create_list_item import create_list_item
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger


async def collect_versions_with_reviewables(project_name: str) -> list[str]:
    """This is used to create a testing list
    The list contains version with published reviewables,
    so it can be used to test... well... lists of versions with reviewable
    """
    result = []

    query = f"""
        SELECT entity_id FROM project_{project_name}.activity_feed
        WHERE
            entity_type = 'version'
        AND activity_type = 'reviewable'
        AND reference_type = 'origin'
        ORDER BY created_at ASC
        LIMIT 10
    """
    async for row in Postgres.iterate(query):
        result.append(row["entity_id"])
    return result


async def materialize_entity_list(
    project_name: str,
    entity_list_id: str,
    *,
    user: UserEntity | None = None,
):
    version_ids = await collect_versions_with_reviewables(project_name)

    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute(f"SET SEARCH_PATH TO project_{project_name}")
        logger.debug("Clearing entity list items")
        await conn.execute(
            "DELETE FROM entity_list_items WHERE entity_list_id = $1",
            entity_list_id,
        )
        for position, version_id in enumerate(version_ids):
            logger.trace(f"Creating list item for version {version_id}")
            await create_list_item(
                project_name,
                entity_list_id,
                "version",
                version_id,
                position=position,
                user=user,
                conn=conn,
                skip_schema_switching=True,
            )

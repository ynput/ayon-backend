from ayon_server.exceptions import AyonException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger


async def get_default_status_for_entity(
    project_name: str,
    entity_type: str,
) -> str:
    """Get default status for an entity."""

    query = f"""
        SELECT name, data FROM project_{project_name}.statuses
        ORDER BY position ASC
    """

    fallback_status: str | None = None

    async for row in Postgres.iterate(query):
        name = row["name"]
        data = row["data"]

        if fallback_status is None:
            fallback_status = name

        if (entity_scope_filter := data.get("scope")) is not None:
            if entity_type not in entity_scope_filter:
                continue

        return name

    if fallback_status is not None:
        logger.warning(
            f"Default status for {entity_type} not found, "
            f"using fallback: {fallback_status}"
        )
        return fallback_status

    raise AyonException("No default status available")

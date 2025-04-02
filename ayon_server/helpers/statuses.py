from ayon_server.exceptions import AyonException
from ayon_server.lib.postgres import Postgres


async def get_default_status_for_entity(
    project_name: str,
    entity_type: str,
) -> str:
    """Get default status for an entity."""

    query = f"""
        SELECT name, data FROM project_{project_name}.statuses
        ORDER BY position ASC
    """

    async for row in Postgres.iterate(query):
        name = row["name"]
        data = row["data"]

        if (entity_scope_filter := data.get("scope")) is not None:
            if entity_type not in entity_scope_filter:
                continue

        return name

    raise AyonException("No default status available")

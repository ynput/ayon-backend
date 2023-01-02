from openpype.exceptions import AyonException
from openpype.lib.postgres import Postgres


async def get_default_status_for_entity(
    project_name: str,
    entity_type: str,
    entity_subtype: str | None = None,
) -> str:
    """Get default status for an entity."""

    query = f"""
        SELECT name, data FROM project_{project_name}.statuses
        ORDER BY position ASC
    """

    async for row in Postgres.iterate(query):
        name = row["name"]
        data = row["data"]

        if (entity_type_filter := data.get("entity_types")) is not None:
            if entity_type not in entity_type_filter:
                continue

        if (entity_subtype_filter := data.get("entity_subtypes")) is not None:
            if entity_subtype not in entity_subtype_filter:
                continue

        return name

    raise AyonException("No default status available")

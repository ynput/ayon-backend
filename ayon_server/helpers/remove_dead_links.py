from ayon_server.lib.postgres import Postgres
from ayon_server.types import ProjectLevelEntityType


async def remove_entity_links(
    project_name: str, entity_type: ProjectLevelEntityType, entity_id: str
) -> None:
    """Remove all links of the given entity"""

    # We actually don't care about the entity type as the ID
    # is unique enough to identify the entity

    _ = entity_type

    query = f"""
        DELETE FROM project_{project_name}.links
        WHERE input_id = $1 OR output_id = $1
    """

    await Postgres.execute(query, entity_id)


async def remove_dead_links(project_name: str) -> None:
    """Remove all links that are not connected to any entity"""

    query = f"""
        SELECT name, input_type, output_type
        FROM project_{project_name}.link_types
    """
    link_types = await Postgres.fetch(query)

    for link_type in link_types:
        # remove inputs

        query = f"""
            DELETE FROM project_{project_name}.links
            WHERE link_type = $1
            AND NOT EXISTS (
                SELECT 1
                FROM project_{project_name}.{link_type['input_type']}s t
                WHERE t.id = links.input_id
            )
        """
        await Postgres.execute(query, link_type["name"])

        # remove outputs

        query = f"""
            DELETE FROM project_{project_name}.links
            WHERE link_type = $1
            AND NOT EXISTS (
                SELECT 1
                FROM project_{project_name}.{link_type['output_type']}s t
                WHERE t.id = links.output_id
            )
        """
        await Postgres.execute(query, link_type["name"])

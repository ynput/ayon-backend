from ayon_server.lib.postgres import Postgres


async def get_used_project_tags(project_name: str) -> list[str]:
    """Returns a list of tags that are used in the project.

    This function is used to get all the tags that are used in the project.
    The tags are collected from all the entities, but don't necessarily
    contain tags defined in the project anatomy.
    """
    result = []
    project_schema = f"project_{project_name.lower()}"
    query = f"""
    SELECT DISTINCT tag FROM (
        SELECT unnest(tags) AS tag FROM {project_schema}.folders
        UNION ALL
        SELECT unnest(tags) FROM {project_schema}.products
        UNION ALL
        SELECT unnest(tags) FROM {project_schema}.tasks
        UNION ALL
        SELECT unnest(tags) FROM {project_schema}.versions
        UNION ALL
        SELECT unnest(tags) FROM {project_schema}.representations
        UNION ALL
        SELECT unnest(tags) FROM {project_schema}.workfiles
    ) t
    """
    async for row in Postgres.iterate(query):
        result.append(row["tag"])
    return result

from ayon_server.lib.postgres import Postgres


async def get_used_project_tags(project_name: str) -> list[str]:
    """Returns a list of tags that are used in the project.

    This function is used to get all the tags that are used in the project.
    The tags are collected from all the entities, but don't necessarily
    contain tags defined in the project anatomy.
    """
    result = []
    async with Postgres.acquire() as conn, conn.transaction():
        project_schema = f"project_{project_name}"
        await conn.execute(f"SET LOCAL search_path TO '{project_schema}'")

        query = """
        SELECT DISTINCT tag FROM (
            SELECT unnest(tags) AS tag FROM folders
            UNION ALL
            SELECT unnest(tags) FROM products
            UNION ALL
            SELECT unnest(tags) FROM tasks
            UNION ALL
            SELECT unnest(tags) FROM versions
            UNION ALL
            SELECT unnest(tags) FROM representations
            UNION ALL
            SELECT unnest(tags) FROM workfiles
        ) t
        """

        async for record in conn.cursor(query):
            result.append(record["tag"])

    return result

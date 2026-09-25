from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis


@Redis.cached("global", "manager-names", ttl=3600)
async def get_manager_names() -> list[str]:
    """
    Returns a set of user names for all users with manager access.
    """
    # This query is optimized to only return the necessary data
    query = """
        SELECT name
        FROM users
        WHERE data->>'isManager' = 'true'
        OR data->>'isAdmin' = 'true'
    """
    res = await Postgres.fetch(query)
    return [row["name"] for row in res]

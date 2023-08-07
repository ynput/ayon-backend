from ayon_server.lib.postgres import Postgres


async def admin_exists() -> bool:
    async for row in Postgres.iterate(
        "SELECT name FROM users WHERE data->>'isAdmin' = 'true'"
    ):
        return True
    return False

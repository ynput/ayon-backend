from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel


class UserCounts(OPModel):
    total: int = Field(0, title="Total users")
    active: int = Field(0, title="Active users")
    admins: int = Field(0, title="Admin users")
    managers: int = Field(0, title="Manager users")


async def get_user_counts(saturated: bool) -> UserCounts:
    query = """
    SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE active) AS active,
    COUNT(*) FILTER (WHERE data->>'isAdmin' = 'true') AS admins,
    COUNT(*) FILTER (WHERE data->>'isManager' = 'true') AS managers
    FROM users;
    """

    async for row in Postgres.iterate(query):
        return UserCounts(
            total=row["total"] or 0,
            active=row["active"] or 0,
            admins=row["admins"] or 0,
            managers=row["managers"] or 0,
        )

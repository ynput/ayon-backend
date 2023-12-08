from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel


class UserCounts(OPModel):
    total: int = Field(0, title="Total users", example=69)
    active: int = Field(0, title="Active users", example=42)
    admins: int = Field(0, title="Admin users", example=1)
    managers: int = Field(0, title="Manager users", example=8)


async def get_user_counts(saturated: bool) -> UserCounts | None:
    """Number of total and active users, admins and managers"""

    query = """
    SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE active) AS active,
    COUNT(*) FILTER (WHERE data->>'isAdmin' = 'true') AS admins,
    COUNT(*) FILTER (WHERE data->>'isManager' = 'true') AS managers
    FROM users;
    """

    res = await Postgres.fetch(query)

    if not res:
        return None
    row = res[0]

    return UserCounts(
        total=row["total"] or 0,
        active=row["active"] or 0,
        admins=row["admins"] or 0,
        managers=row["managers"] or 0,
    )

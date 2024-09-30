from typing import Annotated

from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel


class UserCounts(OPModel):
    total: Annotated[int, Field(title="Total users", example=69)] = 0
    active: Annotated[int, Field(title="Active users", example=42)] = 0
    admins: Annotated[int, Field(title="Admin users", example=1)] = 0
    managers: Annotated[int, Field(title="Manager users", example=8)] = 0


async def get_user_counts(
    saturated: bool = False, system: bool = False
) -> UserCounts | None:
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

from typing import Annotated

from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils import get_nickname


class UserCounts(OPModel):
    total: Annotated[int, Field(title="Total users", example=69)] = 0
    active: Annotated[int, Field(title="Active users", example=42)] = 0
    admins: Annotated[int, Field(title="Admin users", example=1)] = 0
    managers: Annotated[int, Field(title="Manager users", example=8)] = 0


class UserStat(OPModel):
    date: str
    users: dict[str, str | None]  # map active users to their pools


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


async def get_user_stats(
    saturated: bool = False, system: bool = False
) -> list[UserStat] | None:
    _ = saturated
    if not system:
        # Collect traffic stats only when we collect system metrics
        return None

    result = []
    query = "SELECT date, users FROM user_stats ORDER BY date DESC limit 65"

    async for row in Postgres.iterate(query):
        date = row.get("date").strftime("%Y-%m-%d")
        users = row.get("users", {})
        if not users:
            continue

        if not saturated:
            users = {get_nickname(u): pdata for u, pdata in users.items()}

        stat = UserStat(date=date, users=users)
        result.append(stat)

    return result or None

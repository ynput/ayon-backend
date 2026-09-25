from typing import Annotated

from ayon_server.helpers.auth_utils import AuthUtils
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils import get_nickname


class UserCounts(OPModel):
    total: Annotated[int, Field(title="Total users", example=69)] = 0
    active: Annotated[int, Field(title="Active users", example=42)] = 0
    admins: Annotated[int, Field(title="Admin users", example=1)] = 0
    managers: Annotated[int, Field(title="Manager users", example=8)] = 0
    services: Annotated[int, Field(title="Service users", example=1)] = 0
    licenses_total: Annotated[int, Field(title="Total licenses", example=42)] = 0
    licenses_used: Annotated[int, Field(title="Used licenses", example=42)] = 0


class UserStat(OPModel):
    date: str
    users: dict[str, str | None]  # map active users to their pools


async def get_user_counts(
    saturated: bool = False, system: bool = False
) -> UserCounts | None:
    """Number of total and active users, admins and managers"""

    # iterating kinda gives us more control over the result,
    # than running counts... we need to match valid pools,
    # handle admins and managers differently... so this is
    # just more flexible

    query = """
        SELECT
            active,
            data->'isAdmin' AS is_admin,
            data->'isManager' AS is_manager,
            data->'isService' AS is_service,
            data->'userPool' AS user_pool
        FROM public.users
    """

    counts = UserCounts()

    valid_pools = set()
    for pool in await AuthUtils.get_user_pools():
        if pool.valid:
            valid_pools.add(pool.id)
            counts.licenses_total += pool.max

    async for row in Postgres.iterate(query):
        if row["is_service"]:
            counts.services += 1
            # do not count service users to total
            continue

        counts.total += 1

        if row["active"]:
            counts.active += 1

        if row["is_admin"]:
            counts.admins += 1
        elif row["is_manager"]:
            # do not count admins to managers if both are set
            counts.managers += 1

        if row["user_pool"] and row["user_pool"] in valid_pools:
            counts.licenses_used += 1

    return counts


async def get_user_stats(
    saturated: bool = False, system: bool = False
) -> list[UserStat] | None:
    _ = saturated
    if not system:
        # Collect traffic stats only when we collect system metrics
        return None

    result = []
    query = "SELECT date, users FROM public.user_stats ORDER BY date DESC limit 65"

    async for row in Postgres.iterate(query):
        date = row["date"].strftime("%Y-%m-%d")
        users = row.get("users", {})
        if not users:
            continue

        if not saturated:
            users = {get_nickname(u): pdata for u, pdata in users.items()}

        stat = UserStat(date=date, users=users)
        result.append(stat)

    return result or None

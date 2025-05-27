import time
from typing import Annotated, Any

from ayon_server.actions.context import ActionContext
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import Field


class ActionConfig(ActionContext):
    value: Annotated[
        dict[str, Any] | None,
        Field(
            title="Action Config",
            description="The configuration of the action within the given context",
            example={"key": "value"},
        ),
    ] = None


# Some consts and queries

REDIS_TTL = 3600 * 24
BUMP_TTL = 3600 * 24 * 7


#
# get / set action config
#


async def get_action_config(hash: str) -> dict[str, Any]:
    """Get action config for the given hash.

    result is cached in Redis for 24 hours.
    If the config is not found in Redis, it is fetched from Postgres.
    We cache empty configs in Redis as well in order to avoid
    unnecessary queries to Postgres.

    `res` object used has the same structure for postgres and redis.
    {`data`: dict, `last_used`: timestamp}

    We use epoch as this is not a user facing value and it is
    just used for caching / clean-ups.

    We only bounce last_used timestamp after 7 days to avoid costly updates
    """

    now = int(time.time())
    res = await Redis.get_json("action-config", hash)
    if res is None:
        res = await Postgres.fetchrow(
            "SELECT data, last_used FROM public.action_config WHERE hash = $1", hash
        )
        res = res or {"last_used": now, "data": {}}
        res = dict(res)
        if res["last_used"] < now - BUMP_TTL:
            await Postgres.execute(
                "UPDATE public.action_config SET last_used = $1 WHERE hash = $2",
                now,
                hash,
            )
        await Redis.set_json("action-config", hash, res, ttl=REDIS_TTL)
    return res["data"] or {}


async def set_action_config(
    hash: str,
    data: dict[str, Any],
    *,
    addon_name: str | None = None,
    addon_version: str | None = None,
    identifier: str | None = None,
    project_name: str | None = None,
    user_name: str | None = None,
) -> None:
    """Set action config for the given hash.

    Additional data should be provided to identify the action
    and the context in the clean-up process.

    (Delete configs for removed users, archived projects, etc.)
    """

    if not data:
        await Postgres.execute("DELETE FROM public.action_config WHERE hash = $1", hash)
        await Redis.delete("action-config", hash)
        return
    now = int(time.time())

    await Postgres.execute(
        """
        INSERT INTO public.action_config (
            hash, data, identifier, addon_name,
            addon_version, project_name, user_name, last_used
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (hash) DO UPDATE
        SET data = $2,
            identifier = $3,
            addon_name = $4,
            addon_version = $5,
            project_name = $6,
            user_name = $7,
            last_used = $8
        WHERE action_config.hash = $1
        """,
        hash,
        data,
        identifier,
        addon_name,
        addon_version,
        project_name,
        user_name,
        now,
    )
    await Redis.delete("action-config", hash)

from typing import Any

from ayon_server.lib.postgres import Postgres


async def deploy_access_groups(access_groups: list[dict[str, Any]]) -> None:
    for access_group in access_groups:
        name = access_group["name"]
        data = access_group["data"]
        forceUpdate = access_group.get("forceUpdate", False)

        if forceUpdate:
            await Postgres.execute(
                """
                INSERT INTO access_groups (name, data)
                VALUES ($1, $2::jsonb) ON CONFLICT (name) DO UPDATE
                SET data = $2::jsonb
                """,
                name,
                data,
            )
        else:
            await Postgres.execute(
                """
                INSERT INTO access_groups (name, data)
                VALUES ($1, $2::jsonb)
                ON CONFLICT (name) DO NOTHING
                """,
                name,
                data,
            )

from typing import Any

from ayon_server.lib.postgres import Postgres


async def deploy_access_groups(access_groups: list[dict[str, Any]]) -> None:
    existing_access_groups = await Postgres.fetch(
        "SELECT name FROM public.access_groups"
    )
    if existing_access_groups:
        return

    await Postgres.execute(
        """INSERT INTO access_groups (name, data) VALUES ('editor', '{}'::jsonb)"""
    )

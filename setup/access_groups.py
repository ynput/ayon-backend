from typing import Any

from ayon_server.lib.postgres import Postgres

DEFAULT_ACCESS_GROUPS = [
    {
        "name": "supervisor",
        "data": {},  # no restrictions
    },
    {
        "name": "artist",
        "data": {
            "create": {"enabled": True},  # restrict folder creation
            "delete": {"enabled": True},  # restrict folder deletion
        },
    },
    {
        "name": "freelancer",
        "data": {
            "create": {"enabled": True},  # restrict folder creation
            "delete": {"enabled": True},  # restrict folder deletion
            "update": {"enabled": True},  # restrict folder update
            "read": {"enabled": True, "access_list": [{"access_type": "assigned"}]},
            "publish": {"enabled": True, "access_list": [{"access_type": "assigned"}]},
        },
    },
]


async def deploy_access_groups(access_groups: list[dict[str, Any]]) -> None:
    if not access_groups:
        res = await Postgres.fetch("SELECT name FROM access_groups LIMIT 1")
        if res:
            # there are already access groups in the database
            # and no explicit access groups are provided,
            # so we don't need to do anything
            return

        # there are no access groups in the database and there are no
        # groups provided, so we need to create the default access groups
        access_groups = DEFAULT_ACCESS_GROUPS

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

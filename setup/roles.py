from typing import Any

from openpype.lib.postgres import Postgres


async def deploy_roles(roles: list[dict[str, Any]]) -> None:
    await Postgres.execute("DELETE FROM public.roles")
    for role in roles:
        await Postgres.execute(
            """
            INSERT INTO public.roles
                (name, project_name, data)
            VALUES
                ($1, $2, $3)
            """,
            role["name"],
            role.get("project_name", "_"),
            role["data"],
        )

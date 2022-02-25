from openpype.lib.postgres import Postgres
from openpype.utils import json_dumps


async def deploy_roles(roles: list[dict]):
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
            json_dumps(role["data"])
        )

from typing import Any

from nxtools import logging

from openpype.auth.utils import create_password
from openpype.lib.postgres import Postgres


async def deploy_users(
    users: list[dict[str, Any]],
    projects: list[str],
) -> None:
    """Create users in the database."""
    for user in users:

        name = user["name"]
        attrib = {}
        data: dict[str, Any] = {}

        for key in ["fullName", "email"]:
            if key in user:
                attrib[key] = user[key]

        for key in ["is_manager", "is_admin"]:
            if key in user:
                data[key] = user[key]

        if "password" in user:
            logging.debug(f"Creating password for user {name}")
            data["password"] = create_password(user["password"])

        data["default_roles"] = user.get("default_roles", [])

        data["roles"] = {
            project_name: data["default_roles"]
            for project_name in projects
            if data["default_roles"]
        }
        for project_name, roles in user.get("roles", {}).items():
            #  roles = list(
            #     set(data["roles"].get(project_name, [])) | set(roles)
            # )
            if roles:
                data["roles"][project_name] = roles
            elif data["roles"].get(project_name):
                del data["roles"][project_name]

        res = await Postgres.fetch("SELECT * FROM users WHERE name = $1", name)
        if res:
            logging.info(f"Updating user {user['name']}")
            await Postgres.execute(
                "UPDATE users SET data = $1, attrib = $2 WHERE name = $3",
                data,
                attrib,
                name,
            )

        else:
            logging.info(f"Creating user {user['name']}")

            await Postgres.execute(
                """
                INSERT INTO public.users (name, active, attrib, data)
                VALUES ($1, TRUE,  $2, $3)
                """,
                name,
                attrib,
                data,
            )

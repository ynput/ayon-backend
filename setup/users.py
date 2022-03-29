from typing import Any

from nxtools import logging

from openpype.auth.utils import create_password
from openpype.lib.postgres import Postgres


async def deploy_users(
    users: list[dict[str, Any]], default_roles: dict[str, Any]
) -> None:
    """Create users in the database."""
    for user in users:

        name = user["name"]
        attrib = {}
        data: dict[str, Any] = {}

        for key in ["fullname", "email"]:
            if key in user:
                attrib[key] = user[key]

        if "password" in user:
            logging.debug(f"Creating password for user {name}")
            data["password"] = create_password(user["password"])

        data["roles"] = {**default_roles, **user.get("roles", {})}

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

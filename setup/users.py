from nxtools import logging
from openpype.utils import json_dumps
from openpype.lib.postgres import Postgres
from openpype.auth import PasswordAuth


async def deploy_users(users: list[dict], default_roles: dict) -> None:
    """Create users in the database."""
    for user in users:

        name = user["name"]
        attrib = {}
        data = {}

        for key in ["fullname", "email"]:
            if key in user:
                attrib[key] = user[key]

        # Only create password when 'password' is set as authentication method
        if hasattr(PasswordAuth, "create_password") and "password" in user:
            logging.debug(f"Creating password for user {name}")
            data["password"] = PasswordAuth.create_password(user["password"])

        data["roles"] = {**default_roles, **user.get("roles", {})}

        res = await Postgres.fetch("SELECT * FROM users WHERE name = $1", name)
        if res:
            logging.info(f"Updating user {user['name']}")
            await Postgres.execute(
                "UPDATE users SET data = $1, attrib = $2 WHERE name = $3",
                json_dumps(data),
                json_dumps(attrib),
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
                json_dumps(attrib),
                json_dumps(data),
            )

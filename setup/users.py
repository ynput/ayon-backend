from typing import Any

from nxtools import logging

from ayon_server.auth.utils import create_password, hash_password
from ayon_server.lib.postgres import Postgres


async def deploy_users(
    users: list[dict[str, Any]],
    projects: list[str],
) -> None:
    """Create users in the database."""
    for user in users:

        name = user["name"]
        attrib = {}
        data: dict[str, Any] = {}

        for key in ("fullName", "email"):
            if key in user:
                attrib[key] = user[key]

        for key in ("isManager", "isAdmin", "isService", "isGuest"):
            if key in user:
                data[key] = user[key]

        if "password" in user:
            logging.debug(f"Creating password for user {name}")
            data["password"] = create_password(user["password"])

        if "apiKey" in user:
            api_key = user["apiKey"]
            logging.debug(f"Creating api key for user {name}")
            api_key_preview = api_key[:4] + "***" + api_key[-4:]
            data["apiKey"] = hash_password(api_key)
            data["apiKeyPreview"] = api_key_preview

        data["defaultRoles"] = user.get("defaultRoles", [])

        data["roles"] = {
            project_name: data["defaultRoles"]
            for project_name in projects
            if data["defaultRoles"]
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
        if res and not user.get("forceUpdate"):
            logging.info(f"{user['name']} already exists. skipping")
            continue

        logging.info(f"Saving user {user['name']}")
        await Postgres.execute(
            """
            INSERT INTO public.users (name, active, attrib, data)
            VALUES ($1, TRUE,  $2, $3)
            ON CONFLICT (name) DO UPDATE
            SET active = TRUE, attrib = $2, data = $3
            """,
            name,
            attrib,
            data,
        )

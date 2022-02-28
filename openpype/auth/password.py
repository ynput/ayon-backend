from nxtools import logging

from openpype.entities import UserEntity
from openpype.lib.postgres import Postgres
from openpype.utils import json_dumps, json_loads

from .session import Session
from .utils import create_password, ensure_password_complexity, hash_password


class PasswordAuth:
    @classmethod
    async def login(cls, name: str, password: str) -> Session.model:
        """Login using username/password credentials.

        Return a SessionModel object if the credentials are valid.
        Return None otherwise.
        """

        name = name.strip().lower()

        # name active attrib data

        result = await Postgres.fetch(
            "SELECT * FROM public.users WHERE name = $1", name
        )
        if not result:
            logging.error(f"User {name} not found")
            return None

        user = UserEntity.from_record(**dict(result[0]))

        if not user.active:
            logging.error(f"User {name} is not active")
            return None

        if "password" not in user.data:
            logging.error(f"User {name} has no password")
            return None

        pass_hash, pass_salt = user.data["password"].split(":")

        if pass_hash != hash_password(password, pass_salt):
            logging.error(f"User {user.name} has wrong password")
            return None

        return await Session.create(user)

    @classmethod
    async def change_password(cls, name: str, password: str) -> None:
        """Change password for a user."""
        if not ensure_password_complexity(password):
            raise ValueError("Password does not meet complexity requirements")

        result = await Postgres.fetch(
            "SELECT data FROM public.users WHERE name = $1", name
        )
        if not result:
            logging.error(f"Unable to change password. User {name} not found")
            return

        user_data = json_loads(result[0][0]) or {}
        user_data["password"] = create_password(password)

        await Postgres.execute(
            "UPDATE public.users SET data = $1 WHERE name = $2",
            json_dumps(user_data),
            name,
        )

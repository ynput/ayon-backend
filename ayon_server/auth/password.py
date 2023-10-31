from fastapi import Request
from nxtools import logging

from ayon_server.auth.session import Session, SessionModel
from ayon_server.auth.utils import (
    create_password,
    ensure_password_complexity,
    hash_password,
)
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres


class PasswordAuth:
    @classmethod
    async def login(
        cls,
        name: str,
        password: str,
        request: Request | None = None,
    ) -> SessionModel | None:
        """Login using username/password credentials.

        Return a SessionModel object if the credentials are valid.
        Return None otherwise.
        """

        name = name.strip()

        # name active attrib data

        result = await Postgres.fetch(
            "SELECT * FROM public.users WHERE name ilike $1", name
        )
        if not result:
            raise ForbiddenException("Invalid login/password combination")

        user = UserEntity.from_record(result[0])

        if user.is_service:
            raise ForbiddenException("Service users cannot log in")

        if not user.active:
            raise ForbiddenException("User is not active")

        if "password" not in user.data:
            raise ForbiddenException("Password login is not enabled for this user")

        pass_hash, pass_salt = user.data["password"].split(":")

        if pass_hash != hash_password(password, pass_salt):
            raise ForbiddenException("Invalid login/password combination")

        return await Session.create(user, request)

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

        user_data = result[0][0] or {}
        user_data["password"] = create_password(password)

        await Postgres.execute(
            "UPDATE public.users SET data = $1 WHERE name = $2",
            user_data,
            name,
        )

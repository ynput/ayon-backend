"""User entity."""

import re
from typing import Any

from nxtools import logging

from ayon_server.access.access_groups import AccessGroups
from ayon_server.access.permissions import Permissions
from ayon_server.auth.utils import (
    create_password,
    ensure_password_complexity,
    hash_password,
)
from ayon_server.constraints import Constraints
from ayon_server.entities.core import TopLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.exceptions import (
    ForbiddenException,
    LowPasswordComplexityException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import AccessType
from ayon_server.utils import SQLTool, dict_exclude


class UserEntity(TopLevelEntity):
    entity_type: str = "user"
    model = ModelSet("user", attribute_library["user"], has_id=False)
    was_active: bool = False

    # Cache for path access lists
    # the structure is as follows:
    # project_name[access_type]: [path1, path2, ...]
    path_access_cache: dict[str, dict[AccessType, list[str]]] = {}

    #
    # Load
    #

    def __init__(
        self,
        payload: dict[str, Any],
        exists: bool = False,
        validate: bool = True,  # deprecated
    ) -> None:
        super().__init__(payload, exists, validate)
        self.was_active = self.active and self.exists

    @classmethod
    async def load(
        cls,
        name: str,
        transaction: Postgres.Connection | Postgres.Transaction | None = None,
    ) -> "UserEntity":
        """Load a user from the database."""

        if not (
            user_data := await Postgres.fetch(
                "SELECT * FROM public.users WHERE name = $1", name
            )
        ):
            raise NotFoundException(f"Unable to load user {name}")
        return cls.from_record(user_data[0])

    #
    # Save
    #

    async def save(
        self,
        transaction: Postgres.Connection | Postgres.Transaction | None = None,
    ) -> bool:
        """Save the user to the database."""

        conn = transaction or Postgres

        if self.active and not self.was_active:
            logging.info(f"Activating user {self.name}")

            if (max_users := await Constraints.check("maxActiveUsers")) is not None:
                max_users = max_users or 1
                res = await conn.fetch(
                    "SELECT count(*) as cnt FROM users WHERE active is TRUE"
                )
                if res and res[0]["cnt"] >= max_users:
                    raise ForbiddenException(
                        f"Maximum number of users ({max_users}) reached"
                    )

        if self.exists:
            data = dict_exclude(
                self.dict(exclude_none=True), ["ctime", "name", "own_attrib"]
            )
            await conn.execute(
                *SQLTool.update(
                    "public.users",
                    f"WHERE name='{self.name}'",
                    **data,
                )
            )
            return True

        await conn.execute(
            *SQLTool.insert(
                "users",
                **dict_exclude(self.dict(exclude_none=True), ["own_attrib"]),
            )
        )
        return True

    #
    # Delete
    #

    async def delete(
        self,
        transaction: Postgres.Connection | Postgres.Transaction | None = None,
    ) -> bool:
        """Delete existing user."""
        if not self.name:
            raise NotFoundException(f"Unable to delete user {self.name}. Not loaded.")

        commit = not transaction
        transaction = transaction or Postgres
        res = await transaction.fetch(
            """
            WITH deleted AS (
                DELETE FROM users
                WHERE name=$1
                RETURNING *
            ) SELECT count(*) FROM deleted;
            """,
            self.name,
        )
        count = res[0]["count"]

        if commit:
            await self.commit(transaction)
        return bool(count)

    #
    # Authorization helpers
    #

    @property
    def is_service(self) -> bool:
        """
        Service accounts have similar rights as administrators,
        but they also can act as a different user (sudo-style)
        """
        return self._payload.data.get("isService", False)

    @property
    def is_admin(self) -> bool:
        if self.is_guest:
            return False
        return self._payload.data.get("isAdmin", False) or self.is_service

    @property
    def is_guest(self) -> bool:
        return self._payload.data.get("isGuest", False)

    @property
    def is_developer(self) -> bool:
        return self._payload.data.get("isDeveloper", False)

    @property
    def is_manager(self) -> bool:
        data = self._payload.data
        return (
            data.get("isManager", False)
            or data.get("isAdmin", False)
            or data.get("isService", False)
        )

    def permissions(self, project_name: str | None) -> Permissions | None:
        """Return user permissions on a given project."""

        if project_name is None:
            return None

        try:
            access_groups = {
                k.lower(): v for k, v in self.data.get("accessGroups", {}).items()
            }
            active_access_groups = access_groups[project_name.lower()]
        except KeyError:
            raise ForbiddenException("No access group assigned on this project")

        return AccessGroups.combine(active_access_groups, project_name)

    def set_password(
        self,
        password: str | None,
        complexity_check: bool = False,
    ) -> None:
        """Set user password."""

        if password is None:
            self._payload.data.pop("password", None)
            return

        if complexity_check and not ensure_password_complexity(password):
            raise LowPasswordComplexityException
        hashed_password = create_password(password)
        self._payload.data["password"] = hashed_password

    def set_api_key(self, api_key: str | None) -> None:
        """Set user api key."""

        if api_key is None:
            self._payload.data.pop("apiKey", None)
            self._payload.data.pop("apiKeyPreview", None)
            return

        assert re.match(r"^[a-zA-Z0-9]{32}$", api_key)
        api_key_preview = api_key[:4] + "***" + api_key[-4:]

        self._payload.data["apiKey"] = hash_password(api_key)
        self._payload.data["apiKeyPreview"] = api_key_preview

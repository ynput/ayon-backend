"""User entity."""

from openpype.access.permissions import Permissions
from openpype.access.roles import Roles
from openpype.auth.utils import create_password, ensure_password_complexity
from openpype.entities.core import TopLevelEntity, attribute_library
from openpype.entities.models import ModelSet
from openpype.exceptions import (
    ForbiddenException,
    LowPasswordComplexityException,
    NotFoundException,
)
from openpype.lib.postgres import Postgres
from openpype.utils import SQLTool, dict_exclude


class UserEntity(TopLevelEntity):
    entity_type: str = "user"
    model = ModelSet("user", attribute_library["user"], has_id=False)

    #
    # Load
    #

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
        Service accounts have similar rights as managers,
        but they also can act as a different user (sudo-style)
        """
        return self._payload.data.get("isService", False)

    @property
    def is_admin(self) -> bool:
        return self._payload.data.get("isAdmin", False)

    @property
    def is_guest(self) -> bool:
        return self._payload.data.get("isGuest", False)

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
            roles = {k.lower(): v for k, v in self.data.get("roles", {}).items()}
            active_roles = roles[project_name.lower()]
        except KeyError:
            raise ForbiddenException("No role assigned on this project")

        return Roles.combine(active_roles, project_name)

    def set_password(self, password: str) -> None:
        """Set user password."""
        if not ensure_password_complexity(password):
            raise LowPasswordComplexityException
        hashed_password = create_password(password)
        self._payload.data["password"] = hashed_password

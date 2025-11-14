"""User entity."""

import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Optional

from ayon_server.access.access_groups import AccessGroups
from ayon_server.access.permissions import Permissions
from ayon_server.auth.utils import (
    create_password,
    hash_password,
    validate_password,
)
from ayon_server.constraints import Constraints
from ayon_server.entities.core import TopLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.entities.project import ProjectEntity
from ayon_server.exceptions import (
    ConstraintViolationException,
    ForbiddenException,
    NotFoundException,
    ServiceUnavailableException,
)
from ayon_server.helpers.email import send_mail
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import AccessType
from ayon_server.utils import SQLTool, dict_exclude

if TYPE_CHECKING:
    from ayon_server.api.clientinfo import ClientInfo
    from ayon_server.auth.session import SessionModel
    from ayon_server.entities.project import ProjectEntity


class SessionInfo:
    is_api_key: bool = False
    client_info: Optional["ClientInfo"] = None
    token: str | None = None

    def __init__(self, session: "SessionModel") -> None:
        self.is_api_key = session.is_api_key
        self.client_info = session.client_info

    def __repr__(self) -> str:
        return f"SessionInfo(is_api_key={self.is_api_key})"


class UserEntity(TopLevelEntity):
    entity_type: str = "user"
    model = ModelSet("user", attribute_library["user"], has_id=False)
    was_active: bool = False
    original_email: str | None = None
    session: SessionInfo | None = None

    # Cache for path access lists
    # the structure is as follows:
    # project_name[access_type]: [path1, path2, ...]
    path_access_cache: dict[str, dict[AccessType, list[str]]] | None = None
    save_hooks: list[Callable[["UserEntity"], Awaitable[None]]] = []
    _teams: set[str] | None = None

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
        self.was_service = self.is_service and self.exists
        self.original_email = self.attrib.email

    @classmethod
    async def load(
        cls,
        name: str,
        for_update: bool = False,
        *args,
        **kwargs: Any,
    ) -> "UserEntity":
        """Load a user from the database."""

        query = f"""
            SELECT * FROM public.users WHERE name = $1
            {'FOR UPDATE' if for_update else ''}
            """

        try:
            user_data = await Postgres.fetchrow(query, name)
        except Postgres.LockNotAvailableError:
            raise ServiceUnavailableException(
                f"User {name} is locked by another operation"
            )

        if not user_data:
            raise NotFoundException(f"User {name} not found")
        return cls.from_record(user_data)

    def add_session(self, session: "SessionModel") -> None:
        self.session = SessionInfo(session)

    #
    # Save
    #

    async def save(
        self,
        *args,
        run_hooks: bool = True,
        **kwargs,
    ) -> bool:
        """Save the user to the database."""

        async with Postgres.transaction():
            if self.is_service:
                do_con_check = False
                self.data.pop("password", None)  # Service accounts can't have passwords
                self.attrib.email = None  # Nor emails

            elif self.active and not self.was_active:
                # activating previously inactive user
                do_con_check = True

            elif not self.is_service and self.was_service:
                # turning service account into regular user
                # this is still possible via API, but not via UI
                # so we need to check constraints
                do_con_check = True

            else:
                do_con_check = False

            if not self.active:
                self.data.pop("userPool", None)

            if self.attrib.email and (self.attrib.email != self.original_email):
                logger.info(f"Email changed for user {self.name}")
                # Email changed, we need to check if it's unique
                # We cannot use DB index here.
                res = await Postgres.fetch(
                    """
                    SELECT name FROM public.users
                    WHERE LOWER(attrib->>'email') = $1
                    AND name != $2
                    """,
                    self.attrib.email.lower(),
                    self.name,
                )

                if res:
                    msg = "This email is already used by another user"
                    raise ConstraintViolationException(msg)

            if do_con_check:
                logger.info(f"Activating user {self.name}")

                if (max_users := await Constraints.check("maxActiveUsers")) is not None:
                    max_users = max_users or 1
                    res = await Postgres.fetch(
                        """
                        SELECT count(*) as cnt FROM public.users
                        WHERE active is TRUE
                        AND coalesce(data->>'isService', 'false') != 'true'
                        """
                    )
                    if res and res[0]["cnt"] >= max_users:
                        raise ForbiddenException(
                            f"Maximum number of users ({max_users}) reached"
                        )

            if self.exists:
                data = dict_exclude(
                    self.dict(exclude_none=True), ["ctime", "name", "own_attrib"]
                )
                await Postgres.execute(
                    *SQLTool.update(
                        "public.users",
                        f"WHERE name='{self.name}'",
                        **data,
                    )
                )
            else:
                await Postgres.execute(
                    *SQLTool.insert(
                        "users",
                        **dict_exclude(self.dict(exclude_none=True), ["own_attrib"]),
                    )
                )
                await Redis.delete("user.avatar", self.name)
                self.exists = True

            if run_hooks:
                for hook in self.save_hooks:
                    await hook(self)
            return True

    #
    # Delete
    #

    async def delete(self, *args, **kwargs) -> bool:
        """Delete existing user."""
        if not self.name:
            raise NotFoundException(f"Unable to delete user {self.name}. Not loaded.")

        async with Postgres.transaction():
            res = await Postgres.fetch(
                """
                WITH deleted AS (
                    DELETE FROM public.users
                    WHERE name=$1
                    RETURNING *
                ) SELECT count(*) FROM deleted;
                """,
                self.name,
            )

        # Unassign user from all tasks
        # This may fail if project is deleted (edge case, but happens in tests)
        # so we don't want to run it in the same transaction

        projects = await get_project_list()
        async with Postgres.acquire(force_new=True):
            for project in projects:
                query = f"""
                    UPDATE project_{project.name}.tasks SET
                    assignees = array_remove(assignees, '{self.name}')
                    WHERE '{self.name}' = any(assignees)
                """
                try:
                    await Postgres.execute(query)
                except Postgres.UndefinedTableError:
                    continue

        return res[0]["count"]

    #
    # Authorization helpers
    #

    @property
    def is_service(self) -> bool:
        """
        Service accounts have similar rights as administrators,
        but they also can act as a different user (sudo-style)
        """
        return self.data.get("isService", False)

    @property
    def is_admin(self) -> bool:
        if self.is_guest:
            return False
        return self.data.get("isAdmin", False) or self.is_service

    @property
    def is_guest(self) -> bool:
        return self.data.get("isGuest", False)

    @property
    def is_developer(self) -> bool:
        return self.data.get("isDeveloper", False)

    @property
    def is_manager(self) -> bool:
        data = self.data
        return (
            data.get("isManager", False)
            or data.get("isAdmin", False)
            or data.get("isService", False)
        )

    def check_permissions(
        self, key: str, project_name: str | None = None, **kwargs: Any
    ) -> None:
        """
        Check if user has a specific permission.

        Raise forbidden exception if user does not have the permission.

        common kwargs:
        - addon: str

        """
        if self.is_manager:
            return

        permissions = self.permissions(project_name)

        try:
            group, perm_name = key.split(".")
        except ValueError:
            raise ValueError(f"Invalid permission key {key}")

        perm_group = getattr(permissions, group)
        if group not in ["studio", "project"] and not perm_group.enabled:
            # no restrictions on group (folder access)
            return

        try:
            perm = getattr(perm_group, perm_name)
        except AttributeError:
            raise ForbiddenException(f"Your permissions do not include {key}")
        if not perm:
            pdef = f" {project_name}" if project_name else ""
            raise ForbiddenException(f"You are not allowed to access{pdef} {perm_name}")

        if kwargs.get("write") and int(perm) < 2:
            pdef = f" {project_name}" if project_name else ""
            raise ForbiddenException(f"You are not allowed to modify{pdef} {perm_name}")

    def check_project_access(self, project_name: str) -> None:
        # This method is deprecated and is replaced by ensure_project_access.
        # (which is async and can handle guest users)
        if self.is_manager:
            return

        if self.is_guest:
            raise ForbiddenException(
                "Guest users cannot access projects directly. "
                "Use the guest user management API."
            )

        access_groups = [k.lower() for k in self.data.get("accessGroups", {})]
        if project_name.lower() not in access_groups:
            raise ForbiddenException("No access group assigned on this project")

    async def ensure_project_access(self, project_name: str) -> None:
        if self.is_manager:
            return

        if self.is_guest:
            project = await ProjectEntity.load(project_name)
            guest_users = project.data.get("guestUsers", {})
            if self.attrib.email not in guest_users:
                raise ForbiddenException("You are not invited to this project")

        else:
            access_groups = [k.lower() for k in self.data.get("accessGroups", {})]
            if project_name.lower() not in access_groups:
                raise ForbiddenException("No access group assigned on this project")

    def permissions(self, project_name: str | None = None) -> Permissions:
        """Return user permissions on a given project."""

        if project_name is None:
            active_access_groups = self.data.get("defaultAccessGroups", [])

        else:
            try:
                access_groups = {
                    k.lower(): v for k, v in self.data.get("accessGroups", {}).items()
                }
                active_access_groups = access_groups[project_name.lower()]
            except KeyError:
                raise ForbiddenException("No access group assigned on this project")

        return AccessGroups.combine(active_access_groups, project_name or "_")

    def set_password(
        self,
        password: str | None,
        complexity_check: bool = False,
    ) -> None:
        """Set user password."""

        if password is None:
            self.data.pop("password", None)
            return

        if complexity_check:
            validate_password(password)
        hashed_password = create_password(password)
        self.data["password"] = hashed_password

    def set_api_key(self, api_key: str | None) -> None:
        """Set user api key."""

        if api_key is None:
            self.data.pop("apiKey", None)
            self.data.pop("apiKeyPreview", None)
            return

        assert re.match(r"^[a-zA-Z0-9]{32}$", api_key)
        api_key_preview = api_key[:4] + "***" + api_key[-4:]

        self.data["apiKey"] = hash_password(api_key)
        self.data["apiKeyPreview"] = api_key_preview

    async def send_mail(
        self,
        subject: str,
        text: str | None = None,
        html: str | None = None,
    ) -> None:
        """Send email to user."""

        recipient = self.attrib.email
        if not recipient:
            raise ValueError(f"User {self.name} has no email address")

        if self.attrib.fullName:
            recipient = f"{self.attrib.fullName} <{recipient}>"

        await send_mail([recipient], subject, text, html)

    @staticmethod
    async def parse_exposure_level(user: "UserEntity") -> int:
        if user.is_admin:
            default_level = 900
        elif user.is_manager:
            default_level = 700
        elif user.is_guest:
            default_level = 100
        else:
            default_level = 500
        requested_level = user.data.get("uiExposureLevel")
        if requested_level is not None:
            return min(requested_level, default_level)
        return default_level

    async def get_ui_exposure_level(self) -> int:
        """Get UI exposure level for the user."""
        return await self.parse_exposure_level(self)

    def get_teams(self, project: "ProjectEntity") -> set[str]:
        """Get teams the user is part of in a given project."""
        if self._teams is None:
            result = set()
            teams = project.data.get("teams", [])
            for team in teams:
                members = team.get("members", [])
                for member in members:
                    if member.get("name") == self.name:
                        result.add(team["name"])
                        break
            self._teams = result
        return self._teams

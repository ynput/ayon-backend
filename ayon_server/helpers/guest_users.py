"""
Guest users are stored in the project data

Status can be one of:
 - `pending` - user was invited, but not yet logged in
 - `active` - user has logged in and already accessed the instance

{
    "guestUsers": {
        "user@example.com": {
            "fullName": "User Name",
            "status": "pending",
        }
}
"""

from typing import Any, Literal

from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import BadRequestException, ConflictException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger

GuestUserStatus = Literal["pending", "active"]


class GuestUsers:
    @classmethod
    async def add(
        cls,
        email: str,
        *,
        project_name: str,
        full_name: str | None = None,
    ) -> None:
        """Add an guest user to a project."""

        async with Postgres.transaction():
            project = await ProjectEntity.load(name=project_name, for_update=True)
            guest_users = project.data.get("guestUsers", {})

            if email in guest_users:
                raise ConflictException(
                    f"Guest user {email} already exists in the project."
                )

            if not full_name:
                full_name = email

            guest_users[email] = {
                "fullName": full_name,
                "status": "pending",
            }

            project.data["guestUsers"] = guest_users
            await project.save()

    @classmethod
    async def remove(
        cls,
        email: str,
        *,
        project_name: str,
    ) -> None:
        """Remove an guest user from a project."""

        async with Postgres.transaction():
            project = await ProjectEntity.load(name=project_name, for_update=True)
            guest_users = project.data.get("guestUsers", {})

            if email not in guest_users:
                raise BadRequestException(
                    f"Guest user {email} does not exist in the project."
                )

            del guest_users[email]
            project.data["guestUsers"] = guest_users
            await project.save()  # Assuming save method persists the changes

    @classmethod
    async def exists(
        cls,
        email: str,
        *,
        project_name: str,
    ) -> bool:
        """Ensure the guest user is in the project."""

        async with Postgres.transaction():
            project = await ProjectEntity.load(name=project_name)
            exists = email in project.data.get("guestUsers", {})
            if not exists:
                return False

            status = project.data["guestUsers"][email].get("status", "pending")
            if status == "pending":
                project.data["guestUsers"][email]["status"] = "active"
                await project.save()

                logger.info(
                    f"Guest user {email} is now active in project {project_name}."
                )

            return True

    @classmethod
    async def invite(
        cls,
        email: str,
        *,
        project_name: str,
        full_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Invite an guest user to a project."""

        pass

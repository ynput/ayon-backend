"""
External users are stored in the project data

Status can be one of:
 - `pending` - user was invited, but not yet logged in
 - `active` - user has logged in and already accessed the instance

{
    "externalUsers": {
        "user@example.com": {
            "fullName": "User Name",
            "status": "pending",
        }
}
"""

from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger


async def add_external_user(
    project_name: str,
    email: str,
    *,
    full_name: str | None = None,
) -> None:
    """Add an external user to a project."""

    async with Postgres.transaction():
        project = await ProjectEntity.load(name=project_name, for_update=True)
        external_users = project.data.get("externalUsers", {})

        if email in external_users:
            raise BadRequestException(
                f"External user {email} already exists in the project."
            )

        if not full_name:
            full_name = email

        external_users[email] = {
            "fullName": full_name,
            "status": "pending",
        }

        project.data["externalUsers"] = external_users
        await project.save()


async def remove_external_user(
    project_name: str,
    email: str,
) -> None:
    """Remove an external user from a project."""

    async with Postgres.transaction():
        project = await ProjectEntity.load(name=project_name, for_update=True)
        external_users = project.data.get("externalUsers", {})

        if email not in external_users:
            raise BadRequestException(
                f"External user {email} does not exist in the project."
            )

        del external_users[email]
        project.data["externalUsers"] = external_users
        await project.save()  # Assuming save method persists the changes


async def external_user_exists(project_name: str, email: str) -> bool:
    """Ensure the external user is in the project."""

    async with Postgres.transaction():
        project = await ProjectEntity.load(name=project_name)
        exists = email in project.data.get("externalUsers", {})
        if not exists:
            return False

        status = project.data["externalUsers"][email].get("status", "pending")
        if status == "pending":
            project.data["externalUsers"][email]["status"] = "active"
            await project.save()

            logger.info(
                f"External user {email} is now active in project {project_name}."
            )

        return True

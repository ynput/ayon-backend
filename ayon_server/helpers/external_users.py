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


async def add_external_user(
    project_name: str,
    email: str,
    *,
    full_name: str | None = None,
) -> None:
    """Add an external user to a project."""

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
    await project.save()  # Assuming save method persists the changes


async def remove_external_user(
    project_name: str,
    email: str,
) -> None:
    """Remove an external user from a project."""

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
    project = await ProjectEntity.load(name=project_name)
    return email in project.data.get("externalUsers", {})

"""Delete an existing activity."""

from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.lib.postgres import Postgres

__all__ = ["delete_activity"]


async def delete_activity(
    project_name: str, activity_id: str, user_name: str | None = None
) -> None:
    """Delete an activity.

    if user_name is provided, the activity is deleted
    only if the user is the author.

    If the activity has files, they are unlinked from the activity,
    and their updated_at field is set to the current time.
    That way, the files are not deleted, but file cleaner can remove them
    after a grace period.
    """

    # Load the activity first, so we can check if it really exists
    # and if the user (if provided) is the author.
    query = f"SELECT data FROM project_{project_name}.activities WHERE id = $1"
    res = await Postgres.fetch(query, activity_id)

    if not res:
        raise NotFoundException("Activity not found")

    if user_name:
        data = res[0]["data"]
        if "author" in data and data["author"] != user_name:
            raise ForbiddenException("You are not the author of this activity")

    async with Postgres.acquire() as conn, conn.transaction():
        # Unlink files from the activity
        await Postgres.execute(
            f"""
            UPDATE project_{project_name}.files
            SET activity_id = NULL, updated_at = NOW()
            WHERE activity_id = $1
            """,
            activity_id,
        )

        # Delete the activity
        await Postgres().execute(
            f"""
            DELETE FROM project_{project_name}.activities
            WHERE id = $1
            """,
            activity_id,
        )

    return None

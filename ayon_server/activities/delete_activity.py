"""Delete an existing activity."""

from ayon_server.events.eventstream import EventStream
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.lib.postgres import Postgres

from .models import DO_NOT_TRACK_ACTIVITIES

__all__ = ["delete_activity"]


async def delete_activity(
    project_name: str,
    activity_id: str,
    *,
    user_name: str | None = None,
    is_admin: bool = False,
    sender: str | None = None,
    sender_type: str | None = None,
) -> None:
    """Delete an activity.

    if user_name is provided, the activity is deleted
    only if the user is the author.

    If the activity has files, they are unlinked from the activity,
    and their updated_at field is set to the current time.
    That way, the files are not deleted, but file cleaner can remove them
    after a grace period.
    """

    async with Postgres.transaction():
        # Load the activity first, so we can check if it really exists
        # and if the user (if provided) is the author.
        query = f"""
            SELECT data, activity_type
            FROM project_{project_name}.activities
            WHERE id = $1
        """
        res = await Postgres.fetch(query, activity_id)

        if not res:
            raise NotFoundException("Activity not found")

        if user_name and not is_admin:
            data = res[0]["data"]
            if "author" in data and data["author"] != user_name:
                raise ForbiddenException("You are not the author of this activity")
        activity_type = res[0]["activity_type"]

        # create a summary of the activity before deleting it
        # to notify the clients

        summary_references: list[dict[str, str]] = []
        async for row in Postgres.iterate(
            f"""
            SELECT entity_type, entity_id, reference_type
            FROM project_{project_name}.activity_references
            WHERE activity_id = $1 AND entity_id IS NOT NULL
            """,
            activity_id,
        ):
            summary_references.append(dict(row))

        summary = {
            "activity_id": activity_id,
            "activity_type": activity_type,
            "references": summary_references,
        }

        # delete the activity

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
        await Postgres.execute(
            f"""
            DELETE FROM project_{project_name}.activities
            WHERE id = $1
            """,
            activity_id,
        )

        # Notify the front-end about the deleted activity

        await EventStream.dispatch(
            "activity.deleted",
            project=project_name,
            description=f"Deleted {activity_type} activity",
            summary=summary,
            store=activity_type not in DO_NOT_TRACK_ACTIVITIES,
            user=user_name,
            sender=sender,
            sender_type=sender_type,
        )

    return None

from typing import Any

from nxtools import logging

from ayon_server.activities.models import ActivityReferenceModel
from ayon_server.activities.utils import (
    MAX_BODY_LENGTH,
    extract_mentions,
    is_body_with_checklist,
)
from ayon_server.events.eventstream import EventStream
from ayon_server.exceptions import (
    BadRequestException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres

from .utils import process_activity_files


async def update_activity(
    project_name: str,
    activity_id: str,
    body: str | None = None,
    *,
    files: list[str] | None = None,
    user_name: str | None = None,
    extra_references: list[ActivityReferenceModel] | None = None,
    data: dict[str, Any] | None = None,
    sender: str | None = None,
    sender_type: str | None = None,
    append_files: bool = False,
) -> None:
    """Update an activity."""

    # load the activity

    res = await Postgres.fetch(
        f"""
        SELECT activity_type, body, data FROM project_{project_name}.activities
        WHERE id = $1
        """,
        activity_id,
    )

    if not res:
        raise NotFoundException("Activity not found")

    if body is None:
        body = res[0]["body"]
    assert body is not None, "Body must exist"  # mypy

    activity_type = res[0]["activity_type"]
    if len(body) > MAX_BODY_LENGTH:
        raise BadRequestException(f"{activity_type.capitalize()} body is too long")

    activity_data = res[0]["data"]

    if user_name and (user_name != activity_data["author"]):
        logging.warning(
            f"User {user_name} updated activity {activity_id}"
            f" owned by {activity_data['author']}"
        )
        # raise ForbiddenException("You can only update your own activities")

    if data:
        data.pop("author", None)
        activity_data.update(data)

    activity_data.pop("hasChecklist", None)
    if activity_type == "comment" and is_body_with_checklist(body):
        activity_data["hasChecklist"] = True

    references: set[ActivityReferenceModel] = set(extra_references or [])
    async for row in Postgres.iterate(
        f"""
        SELECT id, entity_type, entity_id, entity_name, reference_type, data
        FROM project_{project_name}.activity_references
        WHERE activity_id = $1
        """,
        activity_id,
    ):
        references.add(
            ActivityReferenceModel(
                id=row["id"],
                reference_type=row["reference_type"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                entity_name=row["entity_name"],
                data=row["data"],
            )
        )

    # Extract mentions from the body
    mentions = extract_mentions(body)

    refs_to_delete = []
    for ref in references:
        if ref.reference_type == "mention":
            if ref not in mentions:
                refs_to_delete.append(ref.id)
    references.update(mentions)

    # Update files

    if files is not None:
        if append_files:
            for f in activity_data.get("files", []):
                if f.get("id") not in files:
                    files.append(f["id"])

        files_data = await process_activity_files(project_name, files)
        if files_data:
            activity_data["files"] = files_data
        else:
            activity_data.pop("files", None)

    # Update the activity

    query = f"""
        UPDATE project_{project_name}.activities
        SET body = $1, data = $2
        WHERE id = $3
        """

    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute(query, body, activity_data, activity_id)

        if files is not None:
            await conn.execute(
                f"""
                UPDATE project_{project_name}.files
                SET
                    activity_id = NULL,
                    updated_at = now()
                WHERE
                    activity_id = $1
                AND NOT (id = ANY($2))
                """,
                activity_id,
                files,
            )

            await conn.execute(
                f"""
                UPDATE project_{project_name}.files
                SET
                    activity_id = $1,
                    updated_at = now()
                WHERE
                    id = ANY($2)
                """,
                activity_id,
                files,
            )

        if refs_to_delete:
            await conn.execute(
                f"""
                DELETE FROM project_{project_name}.activity_references
                WHERE id = ANY($1)
                """,
                refs_to_delete,
            )

        st_ref = await conn.prepare(
            f"""
            INSERT INTO project_{project_name}.activity_references
            (
                id,
                activity_id,
                reference_type,
                entity_type,
                entity_id,
                entity_name,
                data,
                created_at,
                updated_at
            )
            VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8, $8)
            ON CONFLICT DO NOTHING
            """
        )

        await st_ref.executemany(
            ref.insertable_tuple(activity_id) for ref in references
        )

    # Notify the front-end about the update

    summary_references: list[dict[str, str]] = []
    for ref in references:
        if ref.entity_id:
            summary_references.append(
                {
                    "entity_id": ref.entity_id,
                    "entity_type": ref.entity_type,
                    "reference_type": ref.reference_type,
                }
            )
    summary = {
        "activity_id": activity_id,
        "activity_type": activity_type,
        "references": summary_references,
    }

    await EventStream.dispatch(
        "activity.updated",
        project=project_name,
        description="",
        summary=summary,
        store=False,
        user=user_name,
        sender=sender,
        sender_type=sender_type,
    )

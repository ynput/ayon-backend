from typing import Any

from nxtools import logging

from ayon_server.activities.models import ActivityReferenceModel
from ayon_server.activities.utils import MAX_BODY_LENGTH, extract_mentions
from ayon_server.exceptions import (
    BadRequestException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres


async def update_activity(
    project_name: str,
    activity_id: str,
    body: str,
    user_name: str | None = None,
    extra_references: list[ActivityReferenceModel] | None = None,
    data: dict[str, Any] | None = None,
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

    activity_type = res[0]["activity_type"]
    if len(body) > MAX_BODY_LENGTH:
        raise BadRequestException(f"{activity_type.capitalize()} body is too long")

    activity_data = res[0]["data"]

    if user_name and (user_name != activity_data["author"]):
        logging.warning(
            f"User {user_name} update activity {activity_id}"
            f" owned by {activity_data['author']}"
        )
        # raise ForbiddenException("You can only update your own activities")

    if data:
        data.pop("author", None)
        activity_data.update(data)

    references = []
    async for row in Postgres.iterate(
        f"""
        SELECT id, entity_type, entity_id, entity_name, reference_type, data
        FROM project_{project_name}.activity_references
        WHERE activity_id = $1
        """,
        activity_id,
    ):
        references.append(
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
    references.extend(mentions)

    # Update the activity

    query = f"""
        UPDATE project_{project_name}.activities
        SET body = $1, data = $2
        WHERE id = $3
        """

    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute(query, body, activity_data, activity_id)

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

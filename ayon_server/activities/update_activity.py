from typing import Any

from ayon_server.activities.models import ActivityReferenceModel
from ayon_server.activities.utils import extract_mentions
from ayon_server.exceptions import ForbiddenException, NotFoundException
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
        SELECT body, data FROM project_{project_name}.activities
        WHERE id = $1
        """,
        activity_id,
    )

    if not res:
        raise NotFoundException("Activity not found")

    activity_data = res[0][data]
    if user_name and (user_name != activity_data["user_name"]):
        raise ForbiddenException("You can only update your own activities")

    references = []
    async for row in Postgres.iterate(
        f"""
        SELECT id, entity_id, entity_name, reference_type, data
        FROM project_{project_name}.activity_references
        WHERE activity_id = $1
        """,
        activity_id,
    ):
        references.append(
            ActivityReferenceModel(
                id=row["id"],
                reference_type=row["reference_type"],
                entity_type=row["entity_id"],
                entity_id=row["entity_id"],
                entity_name=row["entity_name"],
                data={},
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
        await conn.execute(query, body, data, activity_id)

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
            (id, activity_id, reference_type, entity_type, entity_id, entity_name, data)
            VALUES
            ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (activity_id, reference_type, entity_id, entity_name)
            DO UPDATE SET data = EXCLUDED.data
        """
        )

        await st_ref.executemany(
            ref.insertable_tuple(activity_id) for ref in references
        )

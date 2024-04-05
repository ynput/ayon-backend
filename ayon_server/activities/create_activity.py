from typing import Any

from ayon_server.activities.models import (
    ActivityReferenceModel,
    ActivityType,
)
from ayon_server.activities.references import get_references_from_entity
from ayon_server.activities.utils import extract_mentions
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid


async def create_activity(
    entity: ProjectLevelEntity,
    activity_type: ActivityType,
    body: str,
    user_name: str | None = None,
    extra_references: list[ActivityReferenceModel] | None = None,
    data: dict[str, Any] | None = None,
):
    """Create an activity.

    extra_references is an optional
    lists of references to entities and users.
    They are autopopulated based on the activity
    body and the current user if not provided.
    """

    project_name: str = entity.project_name
    entity_type: str = entity.entity_type
    entity_id: str = entity.id

    data = data or {}

    data["origin_type"] = entity_type
    data["origin_id"] = entity_id

    #
    # Extract references
    #

    # Origin is always present. Activity is always created for a single entity.

    references = [
        ActivityReferenceModel(
            entity_id=entity_id,
            entity_type=entity_type,
            entity_name=None,
            reference_type="origin",
        ),
        *extract_mentions(body),
        *(extra_references if extra_references else []),
    ]

    if user_name:
        references.append(
            ActivityReferenceModel(
                entity_type="user",
                entity_name=user_name,
                reference_type="author",
                entity_id=None,
            )
        )
        data["author"] = user_name

    references.extend(await get_references_from_entity(entity))

    #
    # Create the activity
    #

    activity_id = create_uuid()

    query = f"""
        INSERT INTO project_{project_name}.activities
        (id, activity_type, body, data)
        VALUES
        ($1, $2, $3, $4)
    """

    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute(query, activity_id, activity_type, body, data)
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

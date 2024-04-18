import datetime
from typing import Any

from ayon_server.activities.models import (
    ActivityReferenceModel,
    ActivityType,
)
from ayon_server.activities.references import get_references_from_entity
from ayon_server.activities.utils import (
    MAX_BODY_LENGTH,
    extract_mentions,
    is_body_with_checklist,
)
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid


async def create_activity(
    entity: ProjectLevelEntity,
    activity_type: ActivityType,
    body: str,
    activity_id: str | None = None,
    user_name: str | None = None,
    extra_references: list[ActivityReferenceModel] | None = None,
    data: dict[str, Any] | None = None,
    timestamp: datetime.datetime | None = None,
) -> str:
    """Create an activity.

    extra_references is an optional
    lists of references to entities and users.
    They are autopopulated based on the activity
    body and the current user if not provided.
    """

    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc)

    if len(body) > MAX_BODY_LENGTH:
        raise BadRequestException(f"{activity_type.capitalize()} body is too long")

    project_name: str = entity.project_name
    entity_type: str = entity.entity_type
    entity_id: str = entity.id

    data = data or {}

    # Origin object (for displaying in mentions etc)

    origin = {
        "type": entity_type,
        "id": entity_id,
        "name": entity.name,
    }
    if hasattr(entity, "label"):
        origin["label"] = entity.label
    data["origin"] = origin

    if activity_type == "comment" and is_body_with_checklist(body):
        data["hasChecklist"] = True

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

    for ref in extract_mentions(body) + (extra_references or []):
        if ref.entity_id == entity_id and ref.entity_type == entity_type:
            # do not self-reference
            continue

        if ref.reference_type == "relation" and ref.entity_id in [
            r.entity_id for r in references
        ]:
            # do not create relations, if there already is a mention
            continue

        references.append(ref)

    #
    # Create the activity
    #

    if not activity_id:
        activity_id = create_uuid()

    query = f"""
        INSERT INTO project_{project_name}.activities
        (id, activity_type, body, data, created_at, updated_at)
        VALUES
        ($1, $2, $3, $4, $5, $5)
    """

    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute(query, activity_id, activity_type, body, data, timestamp)
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
            ON CONFLICT (activity_id, reference_type, entity_id, entity_name)
            DO UPDATE SET data = EXCLUDED.data
        """
        )

        await st_ref.executemany(
            ref.insertable_tuple(activity_id, timestamp) for ref in references
        )

    return activity_id

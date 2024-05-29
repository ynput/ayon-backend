"""Create an activity.

This module exports just one function: create_activity, that creates
an activity record in the database for the given entity including
all necessary references to other entities and users.
"""

__all__ = ["create_activity"]

import datetime
from typing import Any

from ayon_server.activities.models import (
    ActivityReferenceModel,
    ActivityType,
)
from ayon_server.activities.parents import get_parents_from_entity
from ayon_server.activities.references import get_references_from_entity
from ayon_server.activities.utils import (
    MAX_BODY_LENGTH,
    extract_mentions,
    is_body_with_checklist,
    process_activity_files,
)
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid


async def create_activity(
    entity: ProjectLevelEntity,
    activity_type: ActivityType,
    body: str,
    files: list[str] | None = None,
    activity_id: str | None = None,
    user_name: str | None = None,
    extra_references: list[ActivityReferenceModel] | None = None,
    data: dict[str, Any] | None = None,
    timestamp: datetime.datetime | None = None,
) -> str:
    """Create an activity.

    extra_references is an optional list of references to entities and users.
    They are autopopulated based on the activity body and the current
    user if not provided.
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
    if entity_type == "task":
        origin["subtype"] = entity.task_type
    elif entity_type == "folder":
        origin["subtype"] = entity.folder_type
    elif entity_type == "product":
        origin["subtype"] = entity.product_type

    if hasattr(entity, "label"):
        origin["label"] = entity.label
    data["origin"] = origin

    data["parents"] = await get_parents_from_entity(entity)

    if activity_type == "comment" and is_body_with_checklist(body):
        data["hasChecklist"] = True

    #
    # Extract references
    #

    # Origin is always present. Activity is always created for a single entity.

    references: set[ActivityReferenceModel] = set(extra_references or [])

    references.add(
        ActivityReferenceModel(
            entity_id=entity_id,
            entity_type=entity_type,
            entity_name=None,
            reference_type="origin",
        )
    )

    if user_name:
        references.add(
            ActivityReferenceModel(
                entity_type="user",
                entity_name=user_name,
                reference_type="author",
                entity_id=None,
            )
        )
        data["author"] = user_name

    references.update(extract_mentions(body))
    references.update(await get_references_from_entity(entity))

    #
    # Create the activity
    #

    if not activity_id:
        activity_id = create_uuid()

    #
    # Add files
    #

    if files is not None:
        data["files"] = await process_activity_files(project_name, files)

    query = f"""
        INSERT INTO project_{project_name}.activities
        (id, activity_type, body, data, created_at, updated_at)
        VALUES
        ($1, $2, $3, $4, $5, $5)
    """

    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute(query, activity_id, activity_type, body, data, timestamp)

        if files is not None:
            await conn.execute(
                f"""
                UPDATE project_{project_name}.files
                SET
                    activity_id = $1,
                    updated_at = NOW()
                WHERE id = ANY($2)
                """,
                activity_id,
                files,
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
            ON CONFLICT (activity_id, reference_type, entity_id, entity_name)
            DO UPDATE SET data = EXCLUDED.data
        """
        )

        await st_ref.executemany(
            ref.insertable_tuple(activity_id, timestamp) for ref in references
        )

    return activity_id

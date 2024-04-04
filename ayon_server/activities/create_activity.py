from typing import Any

from ayon_server.activities.models import (
    ActivityType,
    EntityReferenceModel,
    UserReferenceModel,
)
from ayon_server.activities.utils import extract_mentions
from ayon_server.lib.postgres import Postgres
from ayon_server.types import ProjectLevelEntityType
from ayon_server.utils import create_uuid


async def create_activity(
    project_name: str,
    entity_type: ProjectLevelEntityType,
    entity_id: str,
    activity_type: ActivityType,
    body: str,
    user_name: str | None = None,
    extra_entity_references: list[EntityReferenceModel] | None = None,
    extra_user_references: list[UserReferenceModel] | None = None,
    data: dict[str, Any] | None = None,
):
    """Create an activity.

    entity_references and user_references are optional
    lists of references to entities and users.
    They are autopopulated based on the activity
    body and the current user if not provided.
    """

    #
    # Extract references
    #

    # Origin is always present. Activity is always created for a single entity.

    entity_references = [
        EntityReferenceModel(
            entity_id=entity_id, entity_type=entity_type, reference_type="origin"
        )
    ]

    # TODO: crawl ancestors

    if extra_entity_references:
        entity_references.extend(extra_entity_references)

    if user_name:
        user_references = [
            UserReferenceModel(user_name=user_name, reference_type="author")
        ]

    if extra_user_references:
        user_references.extend(extra_user_references)

    # Mentions

    entity_mentions, user_mentions = extract_mentions(body)

    if entity_mentions:
        entity_references.extend(entity_mentions)
    if user_mentions:
        user_references.extend(user_mentions)

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

    data = data or {}

    await Postgres.execute(query, activity_id, activity_type, body, data)

    if entity_references:
        query = f"""
            INSERT INTO project_{project_name}.activity_entity_references
            (activity_id, entity_id, entity_type, reference_type)
            VALUES
            ($1, $2, $3, $4)
        """

        for ref in entity_references:
            await Postgres.execute(
                query, activity_id, ref.entity_id, ref.entity_type, ref.reference_type
            )

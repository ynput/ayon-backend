from .models import ActivityType, EntityReferenceModel, UserReferenceModel


async def create_activity(
    project_name: str,
    activity_type: ActivityType,
    body: str,
    entity_references: list[EntityReferenceModel] | None = None,
    user_references: list[UserReferenceModel] | None = None,
    user: str | None = None,  # CurrentUser name
):
    """Create an activity.

    entity_references and user_references are optional
    lists of references to entities and users.
    They are autopopulated based on the activity
    body and the current user if not provided.
    """
    pass

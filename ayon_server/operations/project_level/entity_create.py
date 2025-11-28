from typing import Any

from ayon_server.entities import UserEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.exceptions import BadRequestException, ForbiddenException

from .hooks import OperationHooks
from .models import OperationModel


async def create_project_level_entity(
    entity_class: type[ProjectLevelEntity],
    project_name: str,
    operation: OperationModel,
    user: UserEntity | None,
) -> tuple[str, list[dict[str, Any]], int]:
    assert operation.data is not None, "data is required for create"

    hooks = OperationHooks.hooks()
    if hooks:
        # create a temporary entity to pass to hooks
        # this won't be saved
        temp_payload = entity_class.model.post_model(**operation.data)
        if operation.entity_id is not None:
            temp_payload.id = operation.entity_id  # type: ignore
        temp_entity = entity_class(project_name, temp_payload.dict())
        for hook in hooks:
            await hook(operation, temp_entity, user)

    #
    # Prepare the payload
    #

    payload = entity_class.model.post_model(**operation.data)
    if operation.entity_id is not None:
        payload.id = operation.entity_id  # type: ignore
    payload_dict = payload.dict()

    #
    # Sanity checks
    #

    if operation.entity_type == "version":
        if user and not payload_dict.get("author"):
            payload_dict["author"] = user.name
        if user and not user.is_admin and payload_dict["author"] != user.name:
            raise ForbiddenException("Only admins can create versions for other users")

    elif operation.entity_type == "folder":
        if payload_dict["id"] == payload_dict.get("parent_id"):
            raise BadRequestException("Folder cannot be its own parent")

    #
    # Create the entity and events
    #

    entity = entity_class(project_name, payload_dict)
    if user:
        await entity.ensure_create_access(user)

    description = f"{operation.entity_type.capitalize()} {entity.name} created"
    events = [
        {
            "topic": f"entity.{operation.entity_type}.created",
            "summary": {"entityId": entity.id, "parentId": entity.parent_id},
            "description": description,
            "project": project_name,
            "user": user.name if user else None,
        }
    ]
    await entity.save(auto_commit=False, user_name=user.name if user else None)
    return entity.id, events, 201

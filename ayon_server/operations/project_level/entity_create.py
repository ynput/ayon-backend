from typing import Any

from ayon_server.entities import UserEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Connection

from .models import OperationModel


async def create_project_level_entity(
    entity_class: type[ProjectLevelEntity],
    project_name: str,
    operation: OperationModel,
    user: UserEntity | None,
    transaction: Connection | None = None,
) -> tuple[ProjectLevelEntity, list[dict[str, Any]], int]:
    assert operation.data is not None, "data is required for create"

    payload = entity_class.model.post_model(**operation.data)
    payload_dict = payload.dict()
    if operation.entity_id is not None:
        payload_dict["id"] = operation.entity_id

    #
    # Sanity checks
    #

    if operation.entity_type == "version":
        if user and not payload_dict.get("author"):
            payload_dict["author"] = user.name
        if user and not user.is_admin and payload_dict["author"] != user.name:
            raise ForbiddenException("Only admins can create versions for other users")

    elif operation.entity_type == "workfile":
        if user and not payload_dict.get("created_by"):
            payload_dict["created_by"] = user.name
        if not payload_dict.get("updated_by"):
            payload_dict["updated_by"] = payload_dict["created_by"]

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
    await entity.save(transaction=transaction)
    return entity, events, 201

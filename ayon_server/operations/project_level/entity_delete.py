from typing import Any

from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Connection

from .models import OperationModel


async def delete_project_level_entity(
    entity_class: type[ProjectLevelEntity],
    project_name: str,
    operation: OperationModel,
    user: UserEntity | None,
    transaction: Connection | None = None,
) -> tuple[ProjectLevelEntity, list[dict[str, Any]], int]:
    assert operation.entity_id is not None, "entity_id is required for delete"
    entity = await entity_class.load(project_name, operation.entity_id)

    #
    # Sanity checks
    #

    if user:
        await entity.ensure_delete_access(user)

    if operation.force and user and not user.is_manager:
        raise ForbiddenException("Only managers can force delete")

    #
    # Create events and delete the entity
    #

    description = f"{operation.entity_type.capitalize()} {entity.name} deleted"
    events = [
        {
            "topic": f"entity.{operation.entity_type}.deleted",
            "summary": {"entityId": entity.id, "parentId": entity.parent_id},
            "description": description,
            "project": project_name,
            "user": user.name if user else None,
        }
    ]
    if ayonconfig.audit_trail:
        events[0]["payload"] = {"entityData": entity.dict_simple()}
    await entity.delete(transaction=transaction, force=operation.force)
    return entity, events, 204

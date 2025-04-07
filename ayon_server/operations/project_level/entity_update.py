from typing import Any, cast

from ayon_server.entities import FolderEntity, UserEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.events.patch import build_pl_entity_change_events
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Connection

from .models import OperationModel


async def update_project_level_entity(
    entity_class: type[ProjectLevelEntity],
    project_name: str,
    operation: OperationModel,
    user: UserEntity | None,
    transaction: Connection | None = None,
) -> tuple[ProjectLevelEntity, list[dict[str, Any]], int]:
    assert operation.data is not None, "data is required for update"
    assert operation.entity_id is not None, "entity_id is required for update"

    payload = entity_class.model.patch_model(**operation.data)
    entity = await entity_class.load(
        project_name,
        operation.entity_id,
        for_update=True,
        transaction=transaction,
    )

    #
    # Sanity checks
    #

    thumbnail_only = len(operation.data) == 1 and "thumbnailId" in operation.data

    if user:
        await entity.ensure_update_access(user, thumbnail_only=thumbnail_only)

    if operation.entity_type == "folder":
        folder_entity = cast(FolderEntity, entity)
        has_versions = bool(await folder_entity.get_versions(transaction))
        for key in ("name", "folder_type", "parent_id"):
            if key not in operation.data:
                continue
            old_value = entity.payload.dict(exclude_none=True).get(key)
            new_value = operation.data[key]
            if has_versions and old_value != new_value:
                raise ForbiddenException(
                    f"Cannot change {key} of a folder with published versions"
                )

    if operation.entity_type == "workfile":
        if not payload.updated_by:  # type: ignore
            payload.updated_by = user.name  # type: ignore

    #
    # Create events and update the entity
    #

    events = build_pl_entity_change_events(entity, payload)
    if user:
        for event in events:
            event["user"] = user.name
    entity.patch(payload, user=user)
    await entity.save(transaction=transaction)
    return entity, events, 204

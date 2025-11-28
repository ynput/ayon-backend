from datetime import datetime
from typing import Any, cast

from ayon_server.entities import FolderEntity, UserEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.events.patch import build_pl_entity_change_events
from ayon_server.exceptions import BadRequestException, ForbiddenException
from ayon_server.lib.postgres import Postgres

from .hooks import OperationHooks
from .models import OperationModel


def build_update_query(
    entity_id: str,
    table: str,
    data: dict[str, Any],
    jsonb_columns: set[str] | None = None,
) -> tuple[str, list[Any]]:
    jsonb_columns = jsonb_columns or set()

    sets = []
    params = []

    param_index = 1

    for key, value in data.items():
        if key in jsonb_columns and isinstance(value, dict):
            # JSONB columns handling

            json_expr = f"COALESCE({key}, '{{}}'::jsonb)"

            # First handle all jsonb_set calls
            for subkey, subval in value.items():
                _subkey = subkey.replace("'", "''")
                if subval is not None:
                    json_expr = f"jsonb_set({json_expr}, '{{{_subkey}}}', ${param_index}::jsonb, true)"  # noqa
                    params.append(subval)
                    param_index += 1

            # Then handle removals (value = None removes the key)
            for subkey, subval in value.items():
                if subval is None:
                    _subkey = subkey.replace("'", "''")
                    json_expr = f"{json_expr} - '{_subkey}'"

            sets.append(f"{key} = {json_expr}")

        else:
            sets.append(f"{key} = ${param_index}")
            params.append(value)
            param_index += 1

    query = f"UPDATE {table} SET " + ", ".join(sets) + f" WHERE id = ${param_index}"
    params.append(entity_id)

    return query, params


async def sanitize_folder_update(
    entity: ProjectLevelEntity,
    operation: OperationModel,
    update_payload_dict: dict[str, Any],
) -> None:
    """
    Sanitize folder update operation to ensure that only allowed fields are updated.

    Note: This function modifies the update_payload_dict in place!
    """

    folder_entity = cast(FolderEntity, entity)
    existing_folder_data = folder_entity.payload.dict(exclude_none=True)
    if not operation.force:
        for key in ("name", "folder_type", "parent_id"):
            if key not in update_payload_dict:
                continue
            old_value = existing_folder_data.get(key)
            new_value = update_payload_dict[key]
            if folder_entity.has_versions and old_value != new_value:
                raise ForbiddenException(
                    f"Cannot change {key} of a folder with published versions"
                )

    # Make sure the hierarchy is acyclic

    if "parent_id" in update_payload_dict:
        # parent_id must be different than the folder id
        new_parent_id = update_payload_dict["parent_id"]
        if new_parent_id == entity.id:
            raise BadRequestException("Folder cannot be its own parent")

        # parent_id cannot be one of the folder's descendants
        descendants = await folder_entity.get_folder_descendant_ids()
        if new_parent_id in descendants:
            raise BadRequestException(
                "Folder cannot be moved to one of its descendants"
            )


async def update_project_level_entity(
    entity_class: type[ProjectLevelEntity],
    project_name: str,
    operation: OperationModel,
    user: UserEntity | None,
) -> tuple[str, list[dict[str, Any]], int]:
    assert operation.data is not None, "data is required for update"
    assert operation.entity_id is not None, "entity_id is required for update"

    # We use slightly different ACL logic if only the thumbnail_id is being updated.
    thumbnail_only = len(operation.data) == 1 and (
        "thumbnailId" in operation.data or "thumbnail_id" in operation.data
    )
    entity = await entity_class.load(project_name, operation.entity_id)

    hooks = OperationHooks.hooks()
    if hooks:
        temp_entity = entity_class(project_name, entity.payload.dict())
        temp_entity.inherited_attrib = entity.inherited_attrib.copy()
        temp_payload = entity_class.model.patch_model(**operation.data)
        temp_entity.patch(temp_payload, user=user)

        for hook in hooks:
            await hook(operation, temp_entity, user)

    # Casting the payload to the model class is used to validate the data
    payload = entity_class.model.patch_model(**operation.data)

    # update_payload_dict is a normalized version of the payload
    # that excludes unset fields and contains snake_case variants of the
    # top-level fields. This is the format, that is going to be used
    # in the database update query.

    update_payload_dict = payload.dict(exclude_unset=True, by_alias=False)

    if user:
        await entity.ensure_update_access(user, thumbnail_only=thumbnail_only)

    if operation.entity_type == "folder":
        await sanitize_folder_update(entity, operation, update_payload_dict)

    # Build events for every change
    # Do this before applying the patch, to the entity to detect the changes

    events = build_pl_entity_change_events(entity, payload)
    if user:
        for event in events:
            event["user"] = user.name

    # Apply the patch to the entity, because later, we need to trigger
    # pre_save method of the entity, that expects the payload to be
    # updated (that covers various entity-specific logic, validtion, etc.).

    entity.patch(payload, user=user)

    # Add the following fields directly to update_payload_dict
    # They don't affect the events created, so they don't need to be
    # in the payload pydantic model.

    if "updated_by" not in update_payload_dict:
        if user is not None:
            update_payload_dict["updated_by"] = user.name
        else:
            update_payload_dict["updated_by"] = None

    if "updated_at" not in update_payload_dict:
        update_payload_dict["updated_at"] = datetime.now()

    # Update the entity
    # We do not use standard patch/save method of the entity here,
    # because we want a partial update.

    query, params = build_update_query(
        entity.id,
        f"project_{project_name}.{entity.entity_type}s",
        update_payload_dict,
        jsonb_columns={"data", "attrib", "files", "traits"},
    )

    await entity.pre_save(False)
    await Postgres.execute(query, *params)

    return entity.id, events, 204

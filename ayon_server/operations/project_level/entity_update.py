from datetime import datetime
from typing import Any, cast

from ayon_server.entities import FolderEntity, UserEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.events.patch import build_pl_entity_change_events
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres

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
                if subval is not None:
                    json_expr = f"jsonb_set({json_expr}, '{{{subkey}}}', ${param_index}::jsonb, true)"  # noqa
                    params.append(subval)
                    param_index += 1

            # Then handle removals (value = None removes the key)
            for subkey, subval in value.items():
                if subval is None:
                    json_expr = f"{json_expr} - '{subkey}'"

            sets.append(f"{key} = {json_expr}")

        else:
            sets.append(f"{key} = ${param_index}")
            params.append(value)
            param_index += 1

    query = f"UPDATE {table} SET " + ", ".join(sets) + f" WHERE id = ${param_index}"
    params.append(entity_id)

    return query, params


async def update_project_level_entity(
    entity_class: type[ProjectLevelEntity],
    project_name: str,
    operation: OperationModel,
    user: UserEntity | None,
) -> tuple[ProjectLevelEntity, list[dict[str, Any]], int]:
    assert operation.data is not None, "data is required for update"
    assert operation.entity_id is not None, "entity_id is required for update"

    # Do not lock for update - we use partial updates and the last update
    # will always win.

    entity = await entity_class.load(project_name, operation.entity_id)

    #
    # Sanity checks
    #

    # Casting the payload to the model class is used to validate the data
    payload = entity_class.model.patch_model(**operation.data)

    # update_payload_dict is a normalized version of the payload
    # that exculdes unset fields and contains camel_case variants of the
    # top-level fields. This is the format, that is going to be used
    # in the database update query.
    update_payload_dict = payload.dict(exclude_unset=True, by_alias=False)

    # We use slightly different ACL logic if only the thumbnail_id is being updated.
    thumbnail_only = len(operation.data) == 1 and "thumbnail_id" in update_payload_dict

    if user:
        await entity.ensure_update_access(user, thumbnail_only=thumbnail_only)

    if operation.entity_type == "folder":
        folder_entity = cast(FolderEntity, entity)
        has_versions = bool(await folder_entity.get_versions())
        existing_folder_data = folder_entity.payload.dict(exclude_none=True)
        for key in ("name", "folder_type", "parent_id"):
            if key not in update_payload_dict:
                continue
            old_value = existing_folder_data.get(key)
            new_value = update_payload_dict[key]
            if has_versions and old_value != new_value:
                raise ForbiddenException(
                    f"Cannot change {key} of a folder with published versions"
                )

    # Add the following fields directly to update_payload_dict
    # They don't affect the events created, so they doesn't need to be
    # in the payload pydantic model.

    if operation.entity_type == "workfile":
        if "updated_by" not in update_payload_dict and user is not None:
            # If the updated_by field is not set, we set it to the current user
            update_payload_dict["updated_by"] = user.name

    if "updated_at" not in update_payload_dict:
        update_payload_dict["updated_at"] = datetime.now()

    #
    # Update the entity
    # We do not use standard patch/save method of the entity here,
    # because we want a partial update.
    #

    query, params = build_update_query(
        entity.id,
        f"project_{project_name}.{entity.entity_type}s",
        update_payload_dict,
        jsonb_columns={"data", "attrib", "files", "traits"},
    )

    await entity.pre_save(False)
    await Postgres.execute(query, *params)

    #
    # Build events for every change
    #

    events = build_pl_entity_change_events(entity, payload)
    if user:
        for event in events:
            event["user"] = user.name

    return entity, events, 204

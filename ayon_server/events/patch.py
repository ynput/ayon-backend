from typing import Any

from pydantic import BaseModel

from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.events.base import create_id


def build_pl_entity_change_events(
    original_entity: ProjectLevelEntity,
    patch: BaseModel,
) -> list[dict[str, Any]]:

    patch_data = patch.dict(exclude_none=True)

    result: list[EventModel] = []
    common_data = {
        "project": original_entity.project_name,
        "summary": {"entityId": original_entity.id},
    }

    entity_type = original_entity.entity_type

    if (new_name := patch_data.get("name")) is not None:
        if new_name != original_entity.name:
            description = (
                f"Renamed {entity_type} {original_entity.name} to {patch.name}"
            )
            result.append(
                {
                    # "hash": create_id(),
                    "topic": f"entity.{entity_type}.renamed",
                    "description": description,
                    **common_data,
                }
            )

    if (new_status := patch_data.get("status")) is not None:
        if new_status != original_entity.status:
            description = (
                f"Changed {entity_type} {original_entity.name} status to {patch.status}"
            )
            result.append(
                {
                    # "hash": create_id(),
                    "topic": f"entity.{entity_type}.status_changed",
                    "description": description,
                    **common_data,
                }
            )

    return result

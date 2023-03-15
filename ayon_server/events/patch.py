from typing import Any

from pydantic import BaseModel

from ayon_server.config import ayonconfig
from ayon_server.entities.core import ProjectLevelEntity

EventData = dict[str, Any]


def get_tags_description(entity_desc: str, list1: list[str], list2: list[str]) -> str:
    """Return a human readable description of the changes in tags

    Martin:

    create a function which takes two lists of strings
    as arguments and return a human-readable description of
    changes between the first one and the second one.

    ChatGPT:

    Sure, here is a function that will do that:
    """
    added = set(list2) - set(list1)
    removed = set(list1) - set(list2)

    description = ""
    if added:
        what = entity_desc + (" tag " if len(added) == 1 else " tags ")
        description += f"Added {what}" + ", ".join(added) + ". "
    if removed:
        if added:
            what = ""
        else:
            what = entity_desc + (" tag " if len(removed) == 1 else " tags ")
        description += f"Removed {what} " + ", ".join(removed) + ". "

    return description.strip()


def build_pl_entity_change_events(
    original_entity: ProjectLevelEntity,
    patch: BaseModel,
) -> list[EventData]:
    """Return a list of events triggered by a patch on a project level entity.

    This should be called in every operation that updates a project level entity,
    after source entity is loaded and validated against the ACL, but BEFORE the
    entity is patched and saved.

    Result is a list of dicts, which is - after successful operation - passed as
    kwargs to the dispatch_event function along with `sender` and `user` args
    (which originate from the request).

    Since multiple events can be triggered by a single operation, the list can
    contain multiple dicts. Each dict contains the following keys:

    - topic
    - summary (contains `entityId` and `parentId`)
    - description - human readable description of the event
    - project - name of the project the entity belongs to
    - payload (if needed)

    """

    patch_data = patch.dict(exclude_unset=True)
    entity_type = original_entity.entity_type
    parent_id = original_entity.parent_id

    result: list[EventData] = []
    common_data = {
        "project": original_entity.project_name,
        "summary": {"entityId": original_entity.id, "parentId": parent_id},
    }

    if (new_name := patch_data.get("name")) is not None:
        if new_name != original_entity.name:
            description = (
                f"Renamed {entity_type} {original_entity.name} to {patch.name}"
            )
            result.append(
                {
                    "topic": f"entity.{entity_type}.renamed",
                    "description": description,
                    **common_data,
                }
            )
            if ayonconfig.audit_trail:
                payload = {
                    "oldValue": original_entity.name,
                    "newValue": new_name,
                }
                result[-1]["payload"] = payload

    if (new_status := patch_data.get("status")) is not None:
        if new_status != original_entity.status:
            description = (
                f"Changed {entity_type} {original_entity.name} status to {patch.status}"
            )
            result.append(
                {
                    "topic": f"entity.{entity_type}.status_changed",
                    "description": description,
                    **common_data,
                }
            )
            if ayonconfig.audit_trail:
                payload = {
                    "oldValue": original_entity.status,
                    "newValue": new_status,
                }
                result[-1]["payload"] = payload

    if (new_tags := patch_data.get("tags")) is not None:
        if new_tags != original_entity.tags:
            description = get_tags_description(
                f"{entity_type} {original_entity.name}",
                original_entity.tags,
                patch.tags,
            )
            if description:
                result.append(
                    {
                        "topic": f"entity.{entity_type}.tags_changed",
                        "description": description,
                        **common_data,
                    }
                )
                if ayonconfig.audit_trail:
                    payload = {
                        "oldValue": original_entity.tags,
                        "newValue": new_tags,
                    }
                    result[-1]["payload"] = payload

    if new_attributes := patch_data.get("attrib", {}):
        attr_list = ", ".join(new_attributes.keys())
        description = (
            f"Changed {entity_type} {original_entity.name} attributes: {attr_list}"
        )
        result.append(
            {
                "topic": f"entity.{entity_type}.attrib_changed",
                "description": description,
                **common_data,
            }
        )
        if ayonconfig.audit_trail:
            payload = {
                "oldValue": {
                    k: original_entity.attrib.dict().get(k)
                    for k in new_attributes.keys()
                },
                "newValue": new_attributes,
            }
            result[-1]["payload"] = payload

    return result

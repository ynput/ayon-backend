from typing import Any

from pydantic import BaseModel

from ayon_server.config import ayonconfig
from ayon_server.entities import ProjectEntity
from ayon_server.entities.core import ProjectLevelEntity

EventData = dict[str, Any]


ADDITIONAL_COLUMNS = {
    "data": "data_changed",
    "label": "label_changed",
    "folder_type": "type_changed",
    "task_type": "type_changed",
    "thumbnail_id": "thumbnail_changed",
    "active": "active_changed",
    "assignees": "assignees_changed",
    "product_type": "product_type_changed",
    "author": "author_changed",
    "files": "files_changed",
    "config": "config_changed",  # for projects
    "statuses": "statuses_changed",  # for projects
    "tags": "tags_changed",  # for projects
    "folder_types": "folder_types_changed",  # for projects
    "task_types": "task_types_changed",  # for projects
    "parent_id": "parent_changed",  # for folders
    "folder_id": "folder_changed",  # for tasks and products
    "task_id": "task_changed",  # for workfiles and versions
    "product_id": "product_changed",  # for versions
    "version_id": "version_changed",  # for representations
}


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
        description += f"Added {what}" + ", ".join(added)
    if removed:
        if added:
            what = ""
        else:
            what = entity_desc + (" tag " if len(removed) == 1 else " tags ")
        description += f"Removed {what} " + ", ".join(removed)

    return description.strip()


def build_pl_entity_change_events(
    original_entity: ProjectLevelEntity,
    patch: BaseModel,
) -> list[EventData]:
    """Return a listof events triggered by a patch on a project level entity.

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
        "summary": {
            "entityId": original_entity.id,
            "parentId": parent_id,
            "entityPath": original_entity.path,
        },
    }

    if (new_name := patch_data.get("name")) is not None:
        if new_name != original_entity.name:
            description = (
                f"Renamed {entity_type} {original_entity.path} to {patch.name}"  # type: ignore
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
                f"Changed {entity_type} {original_entity.path} status to {patch.status}"  # type: ignore
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
                f"{entity_type} {original_entity.path}",
                original_entity.tags,
                patch.tags,  # type: ignore
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
        evt = {
            "topic": f"entity.{entity_type}.attrib_changed",
            **common_data,
        }

        old_attributes = original_entity.attrib.dict()
        for key in list(old_attributes.keys()):
            if key not in new_attributes:
                old_attributes.pop(key)
                continue
            if new_attributes.get(key) == old_attributes[key]:
                old_attributes.pop(key, None)
                new_attributes.pop(key, None)

        if ayonconfig.audit_trail:
            evt["payload"] = {
                "oldValue": old_attributes,
                "newValue": new_attributes,
            }

        if new_attributes:
            attr_list = ", ".join(new_attributes.keys())
            evt["description"] = (
                f"Changed {entity_type} {original_entity.path} attributes: {attr_list}"
            )
            result.append(evt)

    for column_name, topic_name in ADDITIONAL_COLUMNS.items():
        if not hasattr(original_entity, column_name):
            continue

        if column_name not in patch_data:
            continue

        if getattr(original_entity, column_name) == patch_data.get(column_name):
            continue

        description = f"Changed {entity_type} {original_entity.path} {column_name}"
        desc_nval = str(patch_data[column_name])
        if len(desc_nval) < 30:
            description += f" to {desc_nval}"
        if column_name == "active":
            if patch_data.get("active"):
                description = (
                    f"{entity_type.capitalize()} {original_entity.path} activated"
                )
            else:
                description = (
                    f"{entity_type.capitalize()} {original_entity.path} deactivated"
                )

        result.append(
            {
                "topic": f"entity.{entity_type}.{topic_name}",
                "description": description,
                **common_data,
            }
        )
        if ayonconfig.audit_trail:
            payload = {
                "oldValue": getattr(original_entity, column_name),
                "newValue": patch_data[column_name],
            }
            result[-1]["payload"] = payload

    return result


def build_project_change_events(
    original_entity: ProjectEntity,
    patch: BaseModel,
) -> list[EventData]:
    patch_data = patch.dict(exclude_unset=True)
    result: list[EventData] = []
    common_data = {"project": original_entity.name}
    oval: Any
    nval: Any

    if new_attributes := patch_data.get("attrib", {}):
        evt: dict[str, Any] = {
            "topic": "entity.project.attrib_changed",
            "description": "Changed project attributes",
            **common_data,
        }
        # we need to compare the values here, because setting,
        # anatomy to project data will always "update"
        # all the attributes
        oval = {}
        nval = {}
        old_attributes = original_entity.attrib.dict()
        for key, new_value in new_attributes.items():
            if old_attributes.get(key) == new_value:
                continue
            oval[key] = old_attributes.get(key)
            nval[key] = new_value

        if oval or nval:
            if ayonconfig.audit_trail:
                payload = {
                    "oldValue": oval,
                    "newValue": nval,
                }
                evt["payload"] = payload

            result.append(evt)

    for column_name, topic_name in ADDITIONAL_COLUMNS.items():
        if not hasattr(original_entity, column_name):
            continue

        if column_name not in patch_data:
            continue

        oval = getattr(original_entity, column_name)
        nval = patch_data.get(column_name)

        # Handle special case for list of dicts
        # (task_types, folder_types, statuses, tags)
        if isinstance(nval, list):
            for item in nval:
                if isinstance(item, dict):
                    item.pop("original_name", None)

        if nval == oval:
            continue

        description = f"Changed project {column_name}"
        if column_name == "active":
            if patch_data.get("active"):
                description = "Project activated"
            else:
                description = "Project deactivated"

        evt = {
            "topic": f"entity.project.{topic_name}",
            "description": description,
            **common_data,
        }
        if ayonconfig.audit_trail:
            payload = {
                "oldValue": oval,
                "newValue": nval,
            }
            evt["payload"] = payload

        result.append(evt)

    # Original entity.project.changed event

    result.append(
        {
            "topic": "entity.project.changed",
            "description": f"Updated project {original_entity.name}",
            **common_data,
        }
    )

    return result

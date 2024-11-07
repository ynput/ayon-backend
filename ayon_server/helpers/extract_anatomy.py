from typing import Any

from ayon_server.entities import ProjectEntity
from ayon_server.entities.models.submodels import LinkTypeModel
from ayon_server.settings.anatomy import Anatomy


def dict2list(src) -> list[dict[str, Any]]:
    return [{"name": k, "original_name": k, **v} for k, v in src.items()]


def process_aux_table(src: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Process auxiliary table."""
    # TODO: isn't this redundant since we have validators on the model?
    result = []
    for data in src:
        result.append({**data, "original_name": data["name"]})
    return result


def process_link_types(src: list[LinkTypeModel]) -> list[dict[str, Any]]:
    """Convert project linktypes sumbmodel to anatomy-style linktypes."""
    result = []
    for ltdata in src:
        row = {
            "link_type": ltdata.link_type,
            "input_type": ltdata.input_type,
            "output_type": ltdata.output_type,
        }
        for key in ["color", "style"]:
            if value := ltdata.data.get(key):
                row[key] = value
        result.append(row)
    return result


def extract_project_anatomy(project: ProjectEntity) -> Anatomy:
    """Extract Anatomy object from ayon ProjectEntity."""

    templates = project.config.get("templates", {}).get("common", {})
    for template_group, template_group_def in project.config.get(
        "templates", {}
    ).items():
        if template_group == "common":
            continue
        templates[template_group] = dict2list(template_group_def)

    result = {
        "templates": templates,
        "roots": dict2list(project.config.get("roots", {})),
        "folder_types": process_aux_table(project.folder_types),
        "task_types": process_aux_table(project.task_types),
        "link_types": process_link_types(project.link_types),
        "statuses": process_aux_table(project.statuses),
        "tags": process_aux_table(project.tags),
        "attributes": project.attrib,
    }

    return Anatomy(**result)

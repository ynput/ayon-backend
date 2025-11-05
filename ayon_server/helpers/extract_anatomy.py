from collections.abc import Sequence
from typing import Any

from ayon_server.entities import ProjectEntity
from ayon_server.entities.models.submodels import LinkTypeModel
from ayon_server.settings.anatomy import (
    Anatomy,
    EntityNaming,
    FolderType,
    LinkType,
    ProductBaseTypes,
    Root,
    Status,
    Tag,
    TaskType,
)


def dict2list(src) -> list[dict[str, Any]]:
    return [{"name": k, "original_name": k, **v} for k, v in src.items()]


def process_link_types(src: Sequence[LinkTypeModel]) -> list[dict[str, Any]]:
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

    return Anatomy(
        templates=templates,
        attributes=project.attrib,
        roots=[Root(**k) for k in dict2list(project.config.get("roots", {}))],
        folder_types=[FolderType(**k) for k in project.folder_types],
        task_types=[TaskType(**k) for k in project.task_types],
        statuses=[Status(**k) for k in project.statuses],
        product_base_types=ProductBaseTypes(
            **project.config.get("productBaseTypes", {})
        ),
        entity_naming=EntityNaming(**project.config.get("entityNaming", {})),
        tags=[Tag(**k) for k in project.tags],
        link_types=[LinkType(**k) for k in process_link_types(project.link_types)],
    )

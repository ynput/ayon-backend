from typing import Any

from openpype.entities.project import ProjectEntity
from openpype.settings.anatomy import Anatomy


async def create_project_from_anatomy(
    name: str,
    code: str,
    anatomy: Anatomy,
    library: bool = False,
) -> None:
    """Deploy a project."""

    task_types = {}
    for task_type in anatomy.task_types:
        task_types[task_type.name] = {
            k: v for k, v in task_type.dict().items() if k != "name"
        }

    folder_types = {}
    for folder_type in anatomy.folder_types:
        folder_types[folder_type.name] = {
            k: v for k, v in folder_type.dict().items() if k != "name"
        }

    #
    # Config
    #

    config: dict[str, Any] = {}
    config["roots"] = {}
    for root in anatomy.roots:
        config["roots"][root.name] = {
            "windows": root.windows,
            "linux": root.linux,
            "darwin": root.darwin,
        }

    config["templates"] = {
        "common": {
            "version_padding": anatomy.templates.version_padding,
            "version": anatomy.templates.version,
            "frame_padding": anatomy.templates.frame_padding,
            "frame": anatomy.templates.frame,
        }
    }
    for template_type in ("work", "publish", "hero", "delivery", "others"):
        template_group = anatomy.templates.dict().get(template_type, [])
        if not template_group:
            continue
        config["templates"][template_type] = {}
        for template in template_group:
            config["templates"][template_type][template["name"]] = {
                k: template[k] for k in template.keys() if k != "name"
            }

    #
    # Create a project entity
    #

    project = ProjectEntity(
        payload={
            "name": name,
            "code": code,
            "library": library,
            "task_types": task_types,
            "folder_types": folder_types,
            "attrib": anatomy.attributes.dict(),  # type: ignore
            "config": config,
        }
    )

    await project.save()

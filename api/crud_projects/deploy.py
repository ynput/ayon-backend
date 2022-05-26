from typing import Any

from crud_projects.router import router
from fastapi import Depends, Response

from openpype.api import ResponseFactory, dep_current_user
from openpype.entities import ProjectEntity, UserEntity
from openpype.exceptions import ForbiddenException
from openpype.settings.anatomy import Anatomy
from openpype.types import Field, OPModel


class DeployProjectRequestModel(OPModel):
    name: str = Field(..., description="Project name")
    anatomy: Anatomy = Field(..., description="Project anatomy")
    library: bool = Field(False, description="Library project")


@router.post(
    "/projects",
    response_class=Response,
    status_code=201,
    responses={
        201: {"content": "", "description": "Project created"},
        409: ResponseFactory.error(409, "Project already exists"),
    },
)
async def deploy_project(
    payload: DeployProjectRequestModel,
    user: UserEntity = Depends(dep_current_user),
):
    """Create a new project using the provided anatomy object.

    Main purpose is to take an anatomy object and transform its contents
    to the project entity (along with additional data such as the project name).
    """

    if not user.is_manager:
        raise ForbiddenException("Only managers can create projects")

    #
    # Folder and task types
    #

    task_types = {}
    for task_type in payload.anatomy.task_types:
        task_types[task_type.name] = {
            k: v for k, v in task_type.dict().items() if k != "name"
        }

    folder_types = {}
    for folder_type in payload.anatomy.folder_types:
        folder_types[folder_type.name] = {
            k: v for k, v in folder_type.dict().items() if k != "name"
        }

    #
    # Config
    #

    config: dict[str, Any] = {}
    config["roots"] = {}
    for root in payload.anatomy.roots:
        config["roots"][root.name] = {
            "windows": root.windows,
            "linux": root.linux,
            "darwin": root.darwin,
        }

    config["templates"] = {
        "common": {
            "version_padding": payload.anatomy.templates.version_padding,
            "version": payload.anatomy.templates.version,
            "frame_padding": payload.anatomy.templates.frame_padding,
            "frame": payload.anatomy.templates.frame,
        }
    }
    for template_type in ["work", "publish", "hero", "delivery", "others"]:
        template_group = payload.anatomy.templates.dict().get(template_type, [])
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
            "name": payload.name,
            "library": payload.library,
            "task_types": task_types,
            "folder_types": folder_types,
            "attrib": payload.anatomy.attributes,
            "config": config,
        }
    )

    await project.save()
    return Response(status_code=201)

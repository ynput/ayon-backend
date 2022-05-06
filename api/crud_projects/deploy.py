from crud_projects.router import router
from fastapi import Depends, Response

from openpype.anatomy import Anatomy
from openpype.api import ResponseFactory, dep_current_user
from openpype.entities import ProjectEntity, UserEntity
from openpype.exceptions import ForbiddenException
from openpype.types import OPModel, Field


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
    """Create a new project using the provided anatomy object."""

    if not user.is_manager:
        raise ForbiddenException("Only managers can create projects")

    task_types = {}
    for task_type in payload.anatomy.task_types:
        task_types[task_type.name] = {}
        if task_type.icon:
            task_types[task_type.name]["icon"] = task_type.icon

    folder_types = {}
    for folder_type in payload.anatomy.folder_types:
        folder_types[folder_type.name] = {}
        if folder_type.icon:
            folder_types[folder_type.name]["icon"] = folder_type.icon

    config = {}
    config["roots"] = {}
    for root in payload.anatomy.roots:
        config["roots"][root.name] = {
            "windows": root.windows,
            "linux": root.linux,
            "darwin": root.darwin,
        }

    config["templates"] = {
        "defaults": {
            "version_padding": payload.anatomy.templates.version_padding,
            "version": payload.anatomy.templates.version,
            "frame_padding": payload.anatomy.templates.frame_padding,
            "frame": payload.anatomy.templates.frame,
        }
    }
    for template_type in ["work", "render", "publish", "hero", "delivery", "others"]:
        config["templates"][template_type] = {}
        for template in payload.anatomy.templates.dict().get(template_type, []):
            config["templates"][template_type][template["name"]] = {
                k: template[k] for k in template.keys() if k != "name"
            }

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

from typing import Any

from fastapi import Depends, Response

from openpype.api import ResponseFactory, dep_current_user, dep_project_name
from openpype.entities import ProjectEntity, UserEntity
from openpype.exceptions import ForbiddenException
from openpype.helpers.deploy_project import anatomy_to_project_data
from openpype.settings.anatomy import Anatomy

from projects.router import router

def dict2list(src) -> list[dict[str, Any]]:
    return [{"name": k, "original_name": k, **v} for k, v in src.items()]


@router.get(
    "/projects/{project_name}/anatomy",
    response_model=Anatomy,
    response_model_exclude_none=True,
    responses={404: ResponseFactory.error(404, "Project not found")},
)
async def get_project_anatomy(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Retrieve a project anatomy."""

    project = await ProjectEntity.load(project_name)

    templates = project.config.get("templates", {}).get("common", {})
    for template_group, template_group_def in project.config.get(
        "templates", {}
    ).items():
        if template_group == "common":
            continue
        templates[template_group] = dict2list(template_group_def)

    return Anatomy(
        templates=templates,
        roots=dict2list(project.config.get("roots", {})),
        folder_types=dict2list(project.folder_types),
        task_types=dict2list(project.task_types),
        attributes=project.attrib,
    )


@router.post("/projects/{project_name}/anatomy", response_class=Response)
async def set_project_anatomy(
    payload: Anatomy,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Set a project anatomy."""

    if not user.is_manager:
        raise ForbiddenException("Only managers can set project anatomy.")

    project = await ProjectEntity.load(project_name)

    patch_data = anatomy_to_project_data(payload)
    patch = ProjectEntity.model.patch_model(**patch_data)
    project.patch(patch)

    await project.save()
    return Response(status_code=204)

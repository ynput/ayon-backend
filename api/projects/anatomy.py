from typing import Any

from fastapi import Depends, Response, Header
from projects.router import router

from openpype.api import ResponseFactory, dep_current_user, dep_project_name
from openpype.entities import ProjectEntity, UserEntity
from openpype.events import dispatch_event
from openpype.exceptions import ForbiddenException
from openpype.helpers.deploy_project import anatomy_to_project_data
from openpype.settings.anatomy import Anatomy


def dict2list(src) -> list[dict[str, Any]]:
    return [{"name": k, "original_name": k, **v} for k, v in src.items()]


def process_aux_table(src: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Process auxiliary table."""
    result = []
    for data in src:
        result.append({**data, "original_name": data["name"]})
    return result


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
        folder_types=process_aux_table(project.folder_types),
        task_types=process_aux_table(project.task_types),
        statuses=process_aux_table(project.statuses),
        tags=process_aux_table(project.tags),
        attributes=project.attrib,
    )


@router.post("/projects/{project_name}/anatomy", response_class=Response)
async def set_project_anatomy(
    payload: Anatomy,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    x_sender: str | None = Header(default=None),
):
    """Set a project anatomy."""

    if not user.is_manager:
        raise ForbiddenException("Only managers can set project anatomy.")

    project = await ProjectEntity.load(project_name)

    patch_data = anatomy_to_project_data(payload)
    patch = ProjectEntity.model.patch_model(**patch_data)
    project.patch(patch)

    await project.save()

    await dispatch_event(
        "entity.update",
        sender=x_sender,
        project=project_name,
        user=user.name,
        description=f"Updated project {project_name} anatomy",
        summary={
            "entityType": "project",
            "name": project_name,
        },
    )

    return Response(status_code=204)

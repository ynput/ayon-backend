from typing import Any

from fastapi import Header

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import ProjectEntity
from ayon_server.events import dispatch_event
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.deploy_project import anatomy_to_project_data
from ayon_server.settings.anatomy import Anatomy

from .router import router


def dict2list(src) -> list[dict[str, Any]]:
    return [{"name": k, "original_name": k, **v} for k, v in src.items()]


def process_aux_table(src: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Process auxiliary table."""
    # TODO: isn't this redundant since we have validators on the model?
    result = []
    for data in src:
        result.append({**data, "original_name": data["name"]})
    return result


@router.get("/projects/{project_name}/anatomy", response_model_exclude_none=True)
async def get_project_anatomy(user: CurrentUser, project_name: ProjectName) -> Anatomy:
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


@router.post("/projects/{project_name}/anatomy")
async def set_project_anatomy(
    payload: Anatomy,
    user: CurrentUser,
    project_name: ProjectName,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
    """Set a project anatomy."""

    if not user.is_manager:
        raise ForbiddenException("Only managers can set project anatomy.")

    project = await ProjectEntity.load(project_name)

    patch_data = anatomy_to_project_data(payload)
    patch = ProjectEntity.model.patch_model(**patch_data)
    project.patch(patch)

    await project.save()

    await dispatch_event(
        "entity.project.changed",
        sender=x_sender,
        project=project_name,
        user=user.name,
        description=f"Project {project_name} anatomy has been changed",
    )

    return EmptyResponse()

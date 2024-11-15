from ayon_server.api.dependencies import CurrentUser, ProjectName, Sender, SenderType
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import ProjectEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.deploy_project import anatomy_to_project_data
from ayon_server.helpers.extract_anatomy import extract_project_anatomy
from ayon_server.settings.anatomy import Anatomy

from .router import router


@router.get("/projects/{project_name}/anatomy")
async def get_project_anatomy(user: CurrentUser, project_name: ProjectName) -> Anatomy:
    """Retrieve a project anatomy."""
    user.check_project_access(project_name)
    project = await ProjectEntity.load(project_name)
    anatomy = extract_project_anatomy(project)
    return anatomy


@router.post("/projects/{project_name}/anatomy", status_code=204)
async def set_project_anatomy(
    payload: Anatomy,
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Set a project anatomy."""

    if not user.is_manager:
        raise ForbiddenException("Only managers can set project anatomy.")

    project = await ProjectEntity.load(project_name)

    patch_data = anatomy_to_project_data(payload)
    patch = ProjectEntity.model.patch_model(**patch_data)
    project.patch(patch)

    await project.save()

    await EventStream.dispatch(
        "entity.project.changed",
        sender=sender,
        sender_type=sender_type,
        project=project_name,
        user=user.name,
        description=f"Project {project_name} anatomy has been changed",
    )

    return EmptyResponse()

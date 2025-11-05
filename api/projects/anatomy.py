from ayon_server.api.dependencies import CurrentUser, ProjectName, Sender, SenderType
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import ProjectEntity
from ayon_server.events import EventStream
from ayon_server.events.patch import build_project_change_events
from ayon_server.helpers.anatomy import get_project_anatomy as _get_project_anatomy
from ayon_server.helpers.deploy_project import anatomy_to_project_data
from ayon_server.settings.anatomy import Anatomy
from ayon_server.utils import RequestCoalescer

from .router import router


@router.get("/projects/{project_name}/anatomy")
async def get_project_anatomy(user: CurrentUser, project_name: ProjectName) -> Anatomy:
    """Retrieve a project anatomy."""
    await user.ensure_project_access(project_name)
    coalesce = RequestCoalescer()
    return await coalesce(_get_project_anatomy, project_name)


@router.post("/projects/{project_name}/anatomy", status_code=204)
async def set_project_anatomy(
    payload: Anatomy,
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Set a project anatomy."""

    user.check_permissions("project.anatomy", project_name, write=True)

    project = await ProjectEntity.load(project_name)
    patch_data = anatomy_to_project_data(payload)
    patch = ProjectEntity.model.patch_model(**patch_data)
    events = build_project_change_events(project, patch)
    project.patch(patch)

    await project.save()

    for event in events:
        await EventStream.dispatch(
            **event,
            sender=sender,
            sender_type=sender_type,
            user=user.name,
        )

    return EmptyResponse()

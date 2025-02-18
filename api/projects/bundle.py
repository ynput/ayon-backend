from ayon_server.api.dependencies import CurrentUser, ProjectName, Sender, SenderType
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import OPModel

from .router import router


class ProjectBundleRequest(OPModel):
    bundle_name: str | None = None


@router.post("/projects/{project_name}/bundle", status_code=204)
async def set_project_bundle(
    user: CurrentUser,
    project_name: ProjectName,
    payload: ProjectBundleRequest,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Set a project anatomy."""

    _ = sender, sender_type

    if not user.is_manager:
        raise ForbiddenException("Only managers can set project bundle")

    async with Postgres.acquire() as conn, conn.transaction():
        project = await ProjectEntity.load(project_name, conn, for_update=True)
        if payload.bundle_name is None:
            project.data.pop("bundleName", None)
        else:
            project.data["bundleName"] = payload.bundle_name
        await project.save(conn)

    return EmptyResponse()

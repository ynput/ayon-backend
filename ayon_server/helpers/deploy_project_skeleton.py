from typing import Any

from ayon_server.entities.project_skeleton import ProjectSkeletonEntity
from ayon_server.events import EventStream
from ayon_server.helpers.deploy_project import anatomy_to_project_data
from ayon_server.settings.anatomy import Anatomy


async def create_project_skeleton_from_anatomy(
    name: str,
    code: str,
    anatomy: Anatomy,
    *,
    library: bool = False,
    user_name: str | None = None,
    data: dict[str, Any] | None = None,
    assign_users: bool = True,
) -> None:

    project_data = anatomy_to_project_data(anatomy)

    project = ProjectSkeletonEntity(
        payload={
            "name": name,
            "code": code,
            "library": library,
            **project_data,
        },
    )

    await project.save()

    await EventStream.dispatch(
        "entity.project_skeleton.created",
        sender="ayon",
        project=project.name,
        user=user_name,
        description=f"Created project {project.name}",
    )

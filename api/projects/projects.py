from fastapi import Header
from nxtools import logging

from ayon_server.api.dependencies import CurrentUser, NewProjectName, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import ProjectEntity
from ayon_server.events import dispatch_event
from ayon_server.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from projects.router import router

#
# [GET]
#


@router.get("/projects/{project_name}", response_model_exclude_none=True)
async def get_project(
    user: CurrentUser,
    project_name: ProjectName,
) -> ProjectEntity.model.main_model:  # type: ignore
    """Retrieve a project by its name."""

    project = await ProjectEntity.load(project_name)
    return project.as_user(user)


#
# [GET] /stats
#


@router.get("/projects/{project_name}/stats")
async def get_project_stats(user: CurrentUser, project_name: ProjectName):
    """Retrieve a project statistics by its name."""

    counts = {}
    for entity in ["folders", "products", "versions", "representations", "tasks"]:
        res = await Postgres.fetch(
            f"""
            SELECT COUNT(id)
            FROM project_{project_name}.{entity}
            """
        )
        counts[entity] = res[0][0]

    return {"counts": counts}


#
# [PUT]
#


@router.put("/projects/{project_name}", status_code=201)
async def create_project(
    put_data: ProjectEntity.model.post_model,  # type: ignore
    user: CurrentUser,
    project_name: NewProjectName,
) -> EmptyResponse:
    """Create a new project.

    Since project has no ID, and a unique name is used as its
    identifier, use PUT request with the name provided in the URL
    to create a new project.

    This is different from the rest of the entities, which use POST
    requests to create new entities with a unique ID.

    Important: this endpoint only creates a project entity. It does
    not handle creating its anatomy and assigning users to the project,
    so it should be used only in special cases, when you need a granular
    control over a project creation process. Use `Deploy project`
    ([POST] /api/projects) for general usage.
    """

    if not user.is_manager:
        raise ForbiddenException("You need to be a manager in order to create projects")

    action = ""

    try:
        project = await ProjectEntity.load(project_name)
        # NOTE: Replacing projects is not (and shoud not be) supported
        # project.replace(put_data)
        # action = "Replaced"
    except NotFoundException:
        project = ProjectEntity(payload=put_data.dict() | {"name": project_name})
        action = "Created"
    else:
        raise ConflictException(f"Project {project_name} already exists")

    await project.save()

    logging.info(f"[PUT] {action} project {project.name}", user=user.name)
    return EmptyResponse(status_code=201)


#
# [PATCH]
#


@router.patch("/projects/{project_name}", status_code=204)
async def update_project(
    patch_data: ProjectEntity.model.patch_model,  # type: ignore
    user: CurrentUser,
    project_name: ProjectName,
    x_sender: str | None = Header(default=None),
):
    """Patch a project.

    Use a PATCH request to partially update a project.
    For example change the name or a particular key in 'data'.
    """

    project = await ProjectEntity.load(project_name)

    if not user.is_manager:
        raise ForbiddenException(
            "You need to be a manager in order to update a project"
        )

    project.patch(patch_data)
    await project.save()

    await dispatch_event(
        "entity.project.changed",
        sender=x_sender,
        project=project_name,
        user=user.name,
        description=f"Updated project {project_name}",
    )
    logging.info(f"[PATCH] Updated project {project.name}", user=user.name)
    return EmptyResponse()


#
# [DELETE]
#


@router.delete("/projects/{project_name}", status_code=204)
async def delete_project(user: CurrentUser, project_name: ProjectName) -> EmptyResponse:
    """Delete a given project including all its entities."""

    project = await ProjectEntity.load(project_name)

    if not user.is_manager:
        raise ForbiddenException("You need to be a manager in order to delete projects")

    await project.delete()
    logging.info(f"[DELETE] Deleted project {project.name}", user=user.name)
    return EmptyResponse()

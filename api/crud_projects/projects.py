from crud_projects.router import router
from fastapi import Depends, Response
from nxtools import logging

from openpype.api import (
    ResponseFactory,
    dep_current_user,
    dep_new_project_name,
    dep_project_name,
)
from openpype.entities import ProjectEntity, UserEntity
from openpype.exceptions import ForbiddenException, NotFoundException
from openpype.lib.postgres import Postgres

#
# [GET]
#


@router.get(
    "/projects/{project_name}",
    response_model=ProjectEntity.model.main_model,
    response_model_exclude_none=True,
    responses={404: ResponseFactory.error(404, "Project not found")},
)
async def get_project(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Retrieve a project by its name."""

    project = await ProjectEntity.load(project_name)
    return project.as_user(user)


#
# [GET] /stats
#


@router.get(
    "/projects/{project_name}/stats",
)
async def get_project_stats(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Retrieve a project statistics by its name."""

    counts = {}
    for entity in ["folders", "subsets", "versions", "representations", "tasks"]:
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


@router.put(
    "/projects/{project_name}",
    response_class=Response,
    status_code=201,
    responses={
        201: {"content": "", "description": "Project created"},
        409: ResponseFactory.error(409, "Project already exists"),
    },
)
async def create_project(
    put_data: ProjectEntity.model.post_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_new_project_name),
):
    """Create a new project.

    Since project has no ID, and a unique name is used as its
    identifier, use PUT request with the name provided in the URL
    to create a new project.

    This is different from the rest of the entities, which use POST
    requests to create new entities with a unique ID.
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
        return Response(status_code=409)

    await project.save()

    logging.info(f"[PUT] {action} project {project.name}", user=user.name)
    return Response(status_code=201)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}",
    status_code=204,
    response_class=Response,
)
async def update_project(
    patch_data: ProjectEntity.model.patch_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
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
    logging.info(f"[PATCH] Updated project {project.name}", user=user.name)
    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}",
    response_class=Response,
    status_code=204,
)
async def delete_project(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Delete a given project including all its entities."""

    project = await ProjectEntity.load(project_name)

    if not user.is_manager:
        raise ForbiddenException("You need to be a manager in order to delete projects")

    await project.delete()
    logging.info(f"[DELETE] Deleted project {project.name}", user=user.name)
    return Response(status_code=204)

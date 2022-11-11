from fastapi import APIRouter, Depends, Response
from nxtools import logging

from openpype.api.dependencies import dep_current_user, dep_project_name, dep_version_id
from openpype.api.responses import EntityIdResponse, ResponseFactory
from openpype.entities import UserEntity, VersionEntity

router = APIRouter(
    tags=["Versions"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)

#
# [GET]
#


@router.get(
    "/projects/{project_name}/versions/{version_id}",
    response_model=VersionEntity.model.main_model,
    response_model_exclude_none=True,
    responses={404: ResponseFactory.error(404, "Versions not found")},
)
async def get_version(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    version_id: str = Depends(dep_version_id),
):
    """Retrieve a version by its ID."""

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_read_access(user)
    return version.as_user(user)


#
# [POST]
#


@router.post(
    "/projects/{project_name}/versions",
    status_code=201,
    response_model=EntityIdResponse,
    responses={
        409: ResponseFactory.error(409, "Coflict"),
    },
)
async def create_version(
    post_data: VersionEntity.model.post_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Create a new version.

    Use a POST request to create a new version (with a new id).
    """

    version = VersionEntity(project_name=project_name, payload=post_data.dict())
    await version.ensure_create_access(user)
    await version.save()
    logging.info(f"[POST] Created version {version.name}", user=user.name)
    return EntityIdResponse(id=version.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/versions/{version_id}",
    status_code=204,
    response_class=Response,
)
async def update_version(
    post_data: VersionEntity.model.patch_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    version_id: str = Depends(dep_version_id),
):
    """Patch (partially update) a version."""

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_update_access(user)
    version.patch(post_data)
    await version.save()
    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/versions/{version_id}",
    response_class=Response,
    status_code=204,
)
async def delete_version(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    version_id: str = Depends(dep_version_id),
):
    """Delete a version."""

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_delete_access(user)
    await version.delete()
    logging.info(f"[DELETE] Deleted version {version.name}", user=user.name)
    return Response(status_code=204)

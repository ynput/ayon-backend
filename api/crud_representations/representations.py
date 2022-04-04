from fastapi import APIRouter, Depends, Response

from openpype.api.dependencies import (
    dep_current_user,
    dep_project_name,
    dep_representation_id,
)
from openpype.api.responses import EntityIdResponse, ResponseFactory
from openpype.entities import RepresentationEntity, UserEntity

router = APIRouter(
    tags=["Representations"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)

#
# [GET]
#


@router.get(
    "/projects/{project_name}/representations/{representation_id}",
    response_model=RepresentationEntity.model.main_model,
    response_model_exclude_none=True,
    responses={404: ResponseFactory.error(404, "Representations not found")},
)
async def get_representation(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    representation_id: str = Depends(dep_representation_id),
):
    """Retrieve a representation by its ID."""

    representation = await RepresentationEntity.load(project_name, representation_id)
    await representation.ensure_read_access(user)
    return representation.as_user(user)


#
# [POST]
#


@router.post(
    "/projects/{project_name}/representations",
    status_code=201,
    response_model=EntityIdResponse,
    responses={
        409: ResponseFactory.error(409, "Coflict"),
    },
)
async def create_representation(
    post_data: RepresentationEntity.model.post_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Create a new representation.

    Use a POST request to create a new representation (with a new id).
    """

    representation = RepresentationEntity(
        project_name=project_name, payload=post_data.dict()
    )
    await representation.save()
    return EntityIdResponse(id=representation.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/representations/{representation_id}",
    status_code=204,
    response_class=Response,
)
async def update_representation(
    post_data: RepresentationEntity.model.patch_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    representation_id: str = Depends(dep_representation_id),
):
    """Patch (partially update) a representation."""

    representation = await RepresentationEntity.load(project_name, representation_id)
    representation.patch(post_data)
    await representation.save()
    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/representations/{representation_id}",
    response_class=Response,
    status_code=204,
)
async def delete_representation(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    representation_id: str = Depends(dep_representation_id),
):
    """Delete a representation."""

    representation = await RepresentationEntity.load(project_name, representation_id)
    await representation.delete()
    return Response(status_code=204)

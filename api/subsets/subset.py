from fastapi import Depends, Response
from pydantic import BaseModel

from openpype.api import (
    ResponseFactory,
    dep_current_user,
    dep_project_name,
    dep_subset_id,
)
from openpype.entities import SubsetEntity, UserEntity
from openpype.utils import EntityID

from .router import router

#
# [GET]
#


@router.get(
    "/projects/{project_name}/subsets/{subset_id}",
    response_model=SubsetEntity.model.main_model,
    responses={404: ResponseFactory.error(404, "Subset not found")},
)
async def get_subset(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    subset_id: str = Depends(dep_subset_id),
):
    """Retrieve a subset by its ID."""

    subset = await SubsetEntity.load(project_name, subset_id)

    return subset.payload


#
# [POST]
#


class PostSubsetResponseModel(BaseModel):
    subsetId: str = EntityID.field("subset")


@router.post(
    "/projects/{project_name}/subsets",
    status_code=201,
    response_model=PostSubsetResponseModel,
    responses={
        409: ResponseFactory.error(409, "Coflict"),
    },
)
async def create_subset(
    post_data: SubsetEntity.model.post_model,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Create a new subset.

    Use a POST request to create a new subset (with a new id).
    """

    subset = SubsetEntity(False, project_name=project_name, **post_data.dict())
    await subset.save()
    return PostSubsetResponseModel(subsetId=subset.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/subsets/{subset_id}",
    status_code=204,
    response_class=Response,
)
async def update_subset(
    post_data: SubsetEntity.model.patch_model,  # noqa
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    subset_id: str = Depends(dep_subset_id),
):
    """Patch (partially update) a subset."""

    subset = await SubsetEntity.load(project_name, subset_id)
    subset.patch(post_data)
    await subset.save()
    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/subsets/{subset_id}",
    response_class=Response,
    status_code=204,
)
async def delete_subset(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    subset_id: str = Depends(dep_subset_id),
):
    """Delete a subset."""

    subset = await SubsetEntity.load(project_name, subset_id)
    await subset.delete()
    return Response(status_code=204)

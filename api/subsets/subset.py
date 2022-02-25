from fastapi import Depends, Response
from nxtools import log_traceback
from pydantic import BaseModel

from openpype.utils import EntityID
from openpype.entities import UserEntity, SubsetEntity
from openpype.exceptions import (
    ConstraintViolationException,
    RecordNotFoundException
)
from openpype.api import (
    ResponseFactory,
    APIException,
    dep_project_name,
    dep_subset_id,
    dep_current_user
)

from .router import router


#
# [GET]
#


@router.get(
    "/projects/{project_name}/subsets/{subset_id}",
    response_model=SubsetEntity.model.main_model,
    responses={
        404: ResponseFactory.error(404, "Subset not found")
    }
)
async def get_subset(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    subset_id: str = Depends(dep_subset_id)
):
    """Retrieve a subset by its ID."""

    try:
        subset = await SubsetEntity.load(
            project_name,
            subset_id
        )
    except RecordNotFoundException:
        raise APIException(404, "subset not found")
    except Exception:
        log_traceback("Unable to load subset")
        raise APIException(500, "Unable to load subset")

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
    }
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
    try:
        await subset.save()
    except ConstraintViolationException as e:
        raise APIException(409, f"Unable to create subset. {e.detail}")
    return PostSubsetResponseModel(subsetId=subset.id)

#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/subsets/{subset_id}",
    status_code=204,
    response_class=Response
)
async def update_subset(
    post_data: SubsetEntity.model.patch_model,  # noqa
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    subset_id: str = Depends(dep_subset_id)
):
    """Patch (partially update) a subset."""

    try:
        subset = await SubsetEntity.load(
            project_name,
            subset_id
        )
    except RecordNotFoundException:
        raise APIException(404, "subset not found")

    subset.patch(post_data)

    try:
        await subset.save()
    except ConstraintViolationException as e:
        raise APIException(409, f"Unable to update subset. {e.detail}")

    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/subsets/{subset_id}",
    response_class=Response,
    status_code=204
)
async def delete_subset(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    subset_id: str = Depends(dep_subset_id)
):
    """Delete a subset."""

    try:
        subset = await SubsetEntity.load(
            project_name,
            subset_id
        )
    except RecordNotFoundException:
        raise APIException(404, "Subset not found")

    await subset.delete()
    return Response(status_code=204)

from fastapi import APIRouter, Depends, Response

from openpype.entities import UserEntity
from openpype.api import ResponseFactory, dep_current_user


#
# Router
#


router = APIRouter(
    prefix="/users",
    tags=["Users"],
    responses={
        401: ResponseFactory.error(401)
    }
)


#
# [GET] /api/users/me
#


@router.get("/me", response_model=UserEntity.model())
async def get_current_user(
    user: UserEntity = Depends(dep_current_user)
):
    """
    Return the current user information (based on the Authorization header).
    This is used for a profile page as well as as an initial check to ensure
    the user is still logged in.
    """
    return user.payload


#
# [PATCH] /api/users/me
#


@router.patch(
    "/me",
    status_code=204,
    response_class=Response,
)
async def update_current_user(
    patch_data: UserEntity.model("patch"), # noqa
    user: UserEntity = Depends(dep_current_user)
):
    """
    Update the current user information (based on the Authorization header).
    This is used for "my profile" page.
    """
    # TODO: limit the fields that can be updated
    return Response(status_code=204)

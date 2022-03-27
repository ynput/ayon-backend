from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from nxtools import logging

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user, dep_user_name
from openpype.entities import UserEntity
from openpype.exceptions import (
    ForbiddenException,
    RecordNotFoundException,
    LowPasswordComplexityException,
)
from openpype.auth.utils import create_password, ensure_password_complexity

#
# Router
#


router = APIRouter(
    prefix="/users", tags=["Users"], responses={401: ResponseFactory.error(401)}
)


#
# [GET] /api/users/me
#


@router.get(
    "/me", response_model=UserEntity.model.main_model, response_model_exclude_none=True
)
async def get_current_user(user: UserEntity = Depends(dep_current_user)):
    """
    Return the current user information (based on the Authorization header).
    This is used for a profile page as well as as an initial check to ensure
    the user is still logged in.
    """
    return user.payload


#
# [GET] /api/users/{username}
#


@router.get(
    "/{user_name}",
    response_model=UserEntity.model.main_model,
    response_model_exclude_none=True,
)
async def get_user(
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
):
    """
    Return the current user information (based on the Authorization header).
    This is used for a profile page as well as as an initial check to ensure
    the user is still logged in.
    """

    if user_name == user.name:
        return user.payload.as_user(user)

    result = UserEntity.load(user_name)

    if user.is_manager:
        return result.payload

    # To normal users, show only colleague's name
    return {"name": result.name}


@router.put(
    "/{user_name}",
    response_class=Response,
    status_code=201,
    responses={
        201: {"content": "", "description": "User created"},
        409: ResponseFactory.error(409, "User already exists"),
    },
)
async def create_user(
    put_data: UserEntity.model.post_model,
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
):
    """Create a new user."""

    if not user.is_manager:
        raise ForbiddenException("You are not allowed to create users")

    try:
        nuser = await UserEntity.load(user_name)
    except RecordNotFoundException:
        nuser = UserEntity(name=user_name, **put_data.dict())
    else:
        return Response(status_code=409)

    await nuser.save()
    return Response(status_code=201)


@router.delete("/{user_name}", response_class=Response, status_code=204)
async def delete_user(
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
):
    logging.info(f"[DELETE] /users/{user_name}")
    if not user.is_manager:
        raise ForbiddenException("You are not allowed to create users")

    target_user = await UserEntity.load(user_name)
    await target_user.delete()

    return Response(status_code=204)


#
# Change password
#


class ChangePasswordRequestModel(BaseModel):
    password: str = Field(
        ...,
        description="New password",
        example="5up3r5ecr3t_p455W0rd.123",
    )


@router.post("/{user_name}/password", status_code=204, response_class=Response)
async def change_password(
    patch_data: ChangePasswordRequestModel,
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
):
    if (user_name != user.name) and not (user.is_manager):
        raise ForbiddenException("Unable to change password")

    target_user = await UserEntity.load(user_name)

    if not ensure_password_complexity(patch_data.password):
        raise LowPasswordComplexityException()

    hashed_password = create_password(patch_data.password)
    target_user._payload.data["password"] = hashed_password
    await target_user.save()
    return Response(status_code=201)


#
# [PATCH] /api/users/me
#


@router.patch(
    "/me",
    status_code=204,
    response_class=Response,
)
async def update_current_user(
    patch_data: UserEntity.model.patch_model,
    user: UserEntity = Depends(dep_current_user),
):
    """
    Update the current user information (based on the Authorization header).
    This is used for "my profile" page.
    """
    # TODO: limit the fields that can be updated
    return Response(status_code=204)

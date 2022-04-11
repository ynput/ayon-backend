from typing import Literal

from fastapi import APIRouter, Depends, Response
from nxtools import logging
from pydantic import BaseModel, Field

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user, dep_user_name
from openpype.auth.utils import create_password, ensure_password_complexity
from openpype.entities import UserEntity
from openpype.exceptions import (
    ForbiddenException,
    LowPasswordComplexityException,
    NotFoundException,
)

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
    "/me",
    operation_id="get_current_user",
    response_model=UserEntity.model.main_model,
    response_model_exclude_none=True,
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
    operation_id="get_user",
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

    result = await UserEntity.load(user_name)

    if user.is_manager:
        return result.payload

    # To normal users, show only colleague's name
    return {"name": result.name}


@router.put(
    "/{user_name}",
    operation_id="create_user",
    response_class=Response,
    status_code=201,
    responses={
        201: {"content": "", "description": "User created"},
        409: ResponseFactory.error(409, "User already exists"),
    },
)
async def create_user(
    put_data: UserEntity.model.post_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
):
    """Create a new user."""

    if not user.is_manager:
        raise ForbiddenException

    try:
        nuser = await UserEntity.load(user_name)
    except NotFoundException:
        nuser = UserEntity(put_data.dict() | {"name": user_name})
    else:
        return Response(status_code=409)

    await nuser.save()
    return Response(status_code=201)


@router.delete(
    "/{user_name}",
    operation_id="delete_user",
    response_class=Response,
    status_code=204,
)
async def delete_user(
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
):
    logging.info(f"[DELETE] /users/{user_name}")
    if not user.is_manager:
        raise ForbiddenException

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


@router.patch(
    "/{user_name}/password",
    operation_id="change_password",
    status_code=204,
    response_class=Response,
)
async def change_password(
    patch_data: ChangePasswordRequestModel,
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
):
    if (user_name != user.name) and not (user.is_manager):
        # Users can only change their own password
        # Managers can change any password
        raise ForbiddenException

    target_user = await UserEntity.load(user_name)

    if not ensure_password_complexity(patch_data.password):
        raise LowPasswordComplexityException

    hashed_password = create_password(patch_data.password)
    target_user.data["password"] = hashed_password
    await target_user.save()
    return Response(status_code=204)


#
# Assign roles
#


class RoleOnProjects(BaseModel):
    role: str = Field(..., description="Role name")
    projects: list[str] | Literal["all"] | None = Field(
        ...,
        description="List of project user has the role on",
    )


class AssignRolesRequestModel(BaseModel):
    roles: list[RoleOnProjects] = Field(default_factory=list)


@router.patch(
    "/{user_name}/roles",
    operation_id="assign_user_roles",
    status_code=204,
    response_class=Response,
)
async def assign_user_roles(
    patch_data: AssignRolesRequestModel,
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
):
    if not user.is_manager:
        raise ForbiddenException("You are not permitted to assign user roles")

    target_user = await UserEntity.load(user_name)

    roles = {**target_user.data.get("roles", {})}
    messages = []
    for role in patch_data.roles:
        if (role.projects is None) and (role.role in roles):
            messages.append(f"Removed user {user_name} role {role.role}")
            del roles[role.role]
            continue
        messages.append(
            f"Assigned '{role.role}' role to {user_name} on projects: "
            + ", ".join(role.projects)
            if type(role.projects) == list
            else "all"
        )
        roles[role.role] = role.projects

    target_user.data["roles"] = roles
    await target_user.save()

    for message in messages:
        logging.info(message, user=user.name)

    return Response(status_code=204)

from fastapi import APIRouter, Depends, Response
from nxtools import logging

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_access_token, dep_current_user, dep_user_name
from openpype.auth.session import Session
from openpype.auth.utils import create_password, ensure_password_complexity
from openpype.entities import UserEntity
from openpype.exceptions import (
    ForbiddenException,
    LowPasswordComplexityException,
    NotFoundException,
)
from openpype.lib.postgres import Postgres
from openpype.types import Field, OPModel

#
# Router
#


router = APIRouter(
    prefix="/users",
    tags=["Users"],
    responses={401: ResponseFactory.error(401)},
)

#
# [GET] /api/users
#

# TODO: do we need this? Or is graphql enough


class UserListItemModel(OPModel):
    name: str


class UserListModel(OPModel):
    users: list[UserListItemModel] = Field(default_factory=list)


@router.get("")
async def list_users():
    pass


#
# [GET] /api/users/me
#


@router.get(
    "/me",
    response_model=UserEntity.model.main_model,
    response_model_exclude_none=True,
)
async def get_current_user(
    user: UserEntity = Depends(dep_current_user),
) -> UserEntity.model.main_model:  # type: ignore
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
) -> UserEntity.model.main_model | dict[str, str]:  # type: ignore
    """
    Return the current user information (based on the Authorization header).
    This is used for a profile page as well as as an initial check to ensure
    the user is still logged in.
    """

    if user_name == user.name:
        return user.as_user(user)

    result = await UserEntity.load(user_name)

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
    put_data: UserEntity.model.post_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
) -> Response:
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
    response_class=Response,
    status_code=204,
)
async def delete_user(
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
) -> Response:
    logging.info(f"[DELETE] /users/{user_name}")
    if not user.is_manager:
        raise ForbiddenException

    target_user = await UserEntity.load(user_name)
    await target_user.delete()

    return Response(status_code=204)


@router.patch(
    "/{user_name}",
    response_class=Response,
    status_code=204,
)
async def patch_user(
    payload: UserEntity.model.patch_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
    access_token: str = Depends(dep_access_token),
) -> Response:
    logging.info(f"[DELETE] /users/{user_name}")

    if user_name == user.name and (not user.is_manager):
        # Normal users can only patch their attributes
        # (such as full name and email)
        payload.data = None
        payload.active = None
    elif not user.is_manager:
        raise ForbiddenException

    target_user = await UserEntity.load(user_name)
    target_user.patch(payload)
    await target_user.save()

    if user_name == user.name:
        await Session.update(access_token, target_user)

    return Response(status_code=204)


#
# Change password
#


class ChangePasswordRequestModel(OPModel):
    password: str = Field(
        ...,
        description="New password",
        example="5up3r5ecr3t_p455W0rd.123",
    )


@router.patch(
    "/{user_name}/password",
    status_code=204,
    response_class=Response,
)
async def change_password(
    patch_data: ChangePasswordRequestModel,
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
) -> Response:
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
# Change login name
#


class ChangeUserNameRequestModel(OPModel):
    new_name: str = Field(
        ...,
        description="New user name",
        example="EvenBetterUser",
    )


@router.patch(
    "/{user_name}/rename",
    status_code=204,
    response_class=Response,
)
async def change_user_name(
    patch_data: ChangeUserNameRequestModel,
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
) -> Response:
    if not user.is_manager:
        raise ForbiddenException

    # TODO: Run all this in a transaction

    await Postgres.execute(
        "UPDATE users SET name = $1 WHERE name = $2",
        patch_data.new_name,
        user_name,
    )

    # Update tasks assignees - since assignees is an array,
    # it won't update automatically (there's no foreign key)

    project_names = [
        row["name"] async for row in Postgres.iterate("SELECT name FROM projects")
    ]

    for project_name in project_names:
        query = f"""
            UPDATE project_{project_name}.tasks SET
            assignees = array_replace(assignees, '{user_name}', '{patch_data.new_name}')
            WHERE '{user_name}' = ANY(assignees)
        """
        await Postgres.execute(query)

    # TODO: Force the user to log out (e.g. invalidate all sessions)
    return Response(status_code=204)


#
# Assign roles
#


class RolesOnProject(OPModel):
    project: str = Field(
        ...,
        description="Project name",
    )
    roles: list[str] = Field(
        ...,
        description="List of user roles on the project",
    )


class AssignRolesRequestModel(OPModel):
    roles: list[RolesOnProject] = Field(
        default_factory=list,
        description="List of roles to assign",
        example=[
            {"project": "project1", "roles": ["artist", "viewer"]},
            {"project": "project2", "roles": ["viewer"]},
        ],
    )


@router.patch(
    "/{user_name}/roles",
    status_code=204,
    response_class=Response,
)
async def assign_user_roles(
    patch_data: AssignRolesRequestModel,
    user: UserEntity = Depends(dep_current_user),
    user_name: str = Depends(dep_user_name),
) -> Response:
    if not user.is_manager:
        raise ForbiddenException("You are not permitted to assign user roles")

    target_user = await UserEntity.load(user_name)

    role_set = target_user.data.get("roles", {})
    for rconf in patch_data.roles:
        project_name = rconf.project
        roles = rconf.roles
        if not roles:
            if project_name in role_set:
                del role_set[project_name]
            continue
        role_set[project_name] = roles

    target_user.data["roles"] = role_set
    await target_user.save()

    return Response(status_code=204)

from typing import Any

from fastapi import APIRouter, Path
from nxtools import logging

from ayon_server.api import ResponseFactory
from ayon_server.api.clientinfo import ClientInfo
from ayon_server.api.dependencies import AccessToken, CurrentUser, UserName
from ayon_server.api.responses import EmptyResponse
from ayon_server.auth.session import Session
from ayon_server.auth.utils import validate_password
from ayon_server.entities import UserEntity
from ayon_server.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import USER_NAME_REGEX, Field, OPModel
from ayon_server.utils import get_nickname, obscure

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

# TODO: REMOVE!


class UserListItemModel(OPModel):
    name: str


class UserListModel(OPModel):
    users: list[UserListItemModel] = Field(default_factory=list)


@router.get("", deprecated=True)
async def list_users():
    """This endpoint is deprecated. Use GraphQL instead."""
    pass


#
# [GET] /api/users/me
#


@router.get("/me", response_model_exclude_none=True)
async def get_current_user(
    user: CurrentUser,
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


@router.get("/{user_name}", response_model_exclude_none=True)
async def get_user(
    user: CurrentUser, user_name: UserName
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

    if (
        user.is_guest
        and user.name != result.name
        and result.data.get("createdBy") != user.name
    ):
        result.name = get_nickname(result.name)
        if result.attrib.email:
            result.attrib.email = obscure(result.attrib.email)
        if result.attrib.fullName:
            result.attrib.fullName = obscure(result.attrib.fullName)
        result.attrib.avatarUrl = None

    # To normal users, show only colleague's name
    return {"name": result.name}


class NewUserModel(UserEntity.model.post_model):  # type: ignore
    password: str | None = Field(None, description="Password for the new user")


def validate_user_data(data: dict[str, Any]):
    try:
        if default_access_groups := data.get("defaultAccessGroups"):
            assert (
                type(default_access_groups) == list
            ), "defaultAccessGroups must be a list"
            assert all(
                type(access_group) == str for access_group in default_access_groups
            ), "defaultAccessGroups must be a list of str"

        if access_groups := data.get("accessGroups"):
            assert type(access_groups) == dict, "accessGroups must be a dict"
            ag_to_remove = []
            for project, ag_list in access_groups.items():
                assert type(project) == str, "project name must be a string"
                assert type(ag_list) == list, "access group list must be a list"
                assert all(
                    type(ag) == str for ag in ag_list
                ), "acces group list must be a list of str"
                if not ag_list:
                    ag_to_remove.append(project)
            for project in ag_to_remove:
                del access_groups[project]

    except AssertionError as e:
        raise BadRequestException(str(e)) from e


@router.put("/{user_name}")
async def create_user(
    put_data: NewUserModel,
    user: CurrentUser,
    user_name: UserName,
) -> EmptyResponse:
    """Create a new user."""

    if not user.is_manager:
        raise ForbiddenException

    validate_user_data(put_data.data)

    if user.is_guest:
        put_data.data["isGuest"] = True

    try:
        nuser = await UserEntity.load(user_name)
    except NotFoundException:
        nuser = UserEntity(put_data.dict() | {"name": user_name})
        nuser.created_by = user.name
    else:
        raise ConflictException("User already exists")

    if put_data.password:
        nuser.set_password(put_data.password, complexity_check=not user.is_admin)
    await nuser.save()
    return EmptyResponse()


@router.delete("/{user_name}")
async def delete_user(user: CurrentUser, user_name: UserName) -> EmptyResponse:
    logging.info(f"[DELETE] /users/{user_name}")
    if not user.is_manager:
        raise ForbiddenException

    target_user = await UserEntity.load(user_name)
    await target_user.delete()

    return EmptyResponse()


@router.patch("/{user_name}")
async def patch_user(
    payload: UserEntity.model.patch_model,  # type: ignore
    user: CurrentUser,
    user_name: UserName,
    access_token: AccessToken,
) -> EmptyResponse:
    logging.info(f"[PATCH] /users/{user_name}")

    if user_name == user.name and (not user.is_manager):
        # Normal users can only patch their attributes
        # (such as full name and email)
        payload.data = {}
        payload.active = None
    elif not user.is_manager:
        raise ForbiddenException("Only managers can modify other users")

    payload.data["updatedBy"] = user.name
    target_user = await UserEntity.load(user_name)

    if target_user.is_admin and (not user.is_admin):
        raise ForbiddenException("Admins can only be modified by other admins")

    if user.is_guest:
        # Guests can only modify themselves and users they created
        if (
            target_user.name != user.name
            and target_user.data.get("createdBy") != user.name
        ):
            raise ForbiddenException(
                "Guests can only modify themselves and their guests"
            )
        # user cannot change any user's guest status
        payload.data.pop("isGuest", None)

    if not user.is_admin:
        # Non-admins cannot change any user's admin status
        payload.data.pop("isAdmin", None)
    elif target_user.name == user.name:
        # Admins cannot demote themselves
        payload.data.pop("isAdmin", None)

    if not user.is_manager:
        # Non-managers cannot change any user's manager status
        payload.data.pop("isManager", None)
    elif target_user.name == user.name:
        # Managers cannot demote themselves
        payload.data.pop("isManager", None)

    validate_user_data(payload.data)

    target_user.patch(payload)
    await target_user.save()

    # TODO: reload service accounts too?
    # if access_token and (user_name == user.name):
    #    await Session.update(access_token, target_user)

    async for session in Session.list(user_name):
        token = session.token
        if not target_user.active:
            await Session.delete(token)
        else:
            await Session.update(token, target_user)

    return EmptyResponse()


#
# Change password
#


class ChangePasswordRequestModel(OPModel):
    password: str | None = Field(
        None,
        description="New password",
        example="5up3r5ecr3t_p455W0rd.123",
    )
    api_key: str | None = Field(
        None,
        title="API Key",
        description="API Key to set to a service user",
        example="1cb4f6a89012a4b6d8a01ee4f67ae0fb",
        regex=r"^[0-9a-f]{32}$",
    )


@router.patch("/{user_name}/password")
async def change_password(
    patch_data: ChangePasswordRequestModel,
    user: CurrentUser,
    user_name: UserName,
) -> EmptyResponse:
    patch_data_dict = patch_data.dict(exclude_unset=True)

    if "password" in patch_data_dict:
        if (user_name != user.name) and not (user.is_manager):
            # Users can only change their own password
            # Managers can change any password
            raise ForbiddenException()

        target_user = await UserEntity.load(user_name)
        target_user.set_password(
            patch_data.password,
            complexity_check=not user.is_admin,
        )

        await target_user.save()
        return EmptyResponse()

    elif "api_key" in patch_data_dict:
        if not user.is_admin:
            raise ForbiddenException()

        target_user = await UserEntity.load(user_name)
        if not target_user.is_service:
            raise BadRequestException(f"{user_name} is not a service account")
        target_user.set_api_key(patch_data.api_key)

        await target_user.save()
        return EmptyResponse()

    raise BadRequestException("No password or API key provided")


class CheckPasswordRequestModel(OPModel):
    password: str = Field(..., title="Password", example="5up3r5ecr3t_p455W0rd.123")


@router.post("/{user_name}/check_password", deprecated=True)
@router.post("/{user_name}/checkPassword")
async def check_password(
    post_data: CheckPasswordRequestModel,
    user: CurrentUser,
    user_name: UserName,
) -> EmptyResponse:
    validate_password(post_data.password)
    return EmptyResponse()


#
# Change login name
#


class ChangeUserNameRequestModel(OPModel):
    new_name: str = Field(
        ...,
        description="New user name",
        example="EvenBetterUser",
        regex=USER_NAME_REGEX,
    )


@router.patch("/{user_name}/rename")
async def change_user_name(
    patch_data: ChangeUserNameRequestModel,
    user: CurrentUser,
    user_name: UserName,
) -> EmptyResponse:
    if not user.is_manager:
        raise ForbiddenException

    async with Postgres.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE users SET name = $1 WHERE name = $2",
                patch_data.new_name,
                user_name,
            )

            # Update tasks assignees - since assignees is an array,
            # it won't update automatically (there's no foreign key)

            projects = await conn.fetch("SELECT name FROM projects")
            project_names = [row["name"] for row in projects]

            for project_name in project_names:
                query = f"""
                    UPDATE project_{project_name}.tasks SET
                    assignees = array_replace(
                        assignees,
                        '{user_name}',
                        '{patch_data.new_name}'
                    )
                    WHERE '{user_name}' = ANY(assignees)
                """
                await conn.execute(query)

    # TODO: Force the user to log out (e.g. invalidate all sessions)
    return EmptyResponse()


#
# Sessions
#


class UserSessionModel(OPModel):
    token: str
    is_service: bool
    last_used: int
    client_info: ClientInfo | None = None


class UserSessionsResponseModel(OPModel):
    sessions: list[UserSessionModel]


@router.get("/{user_name}/sessions")
async def get_user_sessions(
    current_user: CurrentUser, user_name: UserName
) -> UserSessionsResponseModel:
    if (not current_user.is_manager) and (current_user.name != user_name):
        raise ForbiddenException("You are not allowed to list other users' sessions")

    return UserSessionsResponseModel(
        sessions=[
            UserSessionModel(
                token=session.token,
                client_info=session.client_info,
                is_service=session.is_service,
                last_used=session.last_used,
            )
            async for session in Session.list(user_name)
        ]
    )


@router.delete("/{user_name}/sessions/{session_id}")
async def delete_user_session(
    current_user: CurrentUser,
    user_name: UserName,
    session_id: str = Path(...),
) -> EmptyResponse:
    session = await Session.check(session_id, None)
    if not session:
        raise NotFoundException("Requested session id does not exist")
    if session.user.name != current_user.name and (not current_user.is_manager):
        raise ForbiddenException(
            "You are not allowed to delete sessions which don't belong to you"
        )
    await Session.delete(session_id)
    return EmptyResponse()


#
# Assign access groups
#


class AccessGroupsOnProject(OPModel):
    project: str = Field(
        ...,
        description="Project name",
    )
    access_groups: list[str] = Field(
        ...,
        description="List of access groups on the project",
    )


class AssignAccessGroupsRequestModel(OPModel):
    access_groups: list[AccessGroupsOnProject] = Field(
        default_factory=list,
        description="List of access groups to assign",
        example=[
            {"project": "project1", "roles": ["artist", "viewer"]},
            {"project": "project2", "roles": ["viewer"]},
        ],
    )


@router.patch("/{user_name}/accessGroups")
async def assign_access_groups(
    patch_data: AssignAccessGroupsRequestModel,
    user: CurrentUser,
    user_name: UserName,
) -> EmptyResponse:
    if not user.is_manager:
        raise ForbiddenException("You are not permitted to assign access groups")

    target_user = await UserEntity.load(user_name)

    ag_set = target_user.data.get("accessGroups", {})
    for rconf in patch_data.access_groups:
        project_name = rconf.project
        access_groups = rconf.access_groups
        if not access_groups:
            if project_name in ag_set:
                del ag_set[project_name]
            continue
        ag_set[project_name] = access_groups

    target_user.data["accessGroups"] = ag_set
    await target_user.save()

    return EmptyResponse()

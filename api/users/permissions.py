from typing import Annotated, Literal

from ayon_server.access.permissions import (
    Permissions,
    ProjectManagementPermissions,
    StudioManagementPermissions,
)
from ayon_server.api.dependencies import CurrentUser, ProjectName, UserName
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField

from .router import router

manager_permissions = Permissions(
    studio=StudioManagementPermissions(create_projects=True, list_all_users=True),
    project=ProjectManagementPermissions(anatomy=2, access=2, settings=2),
    # we use defaults for folder access and so on
)

UserLevel = Literal["admin", "manager", "user"]


class UserPermissionsModel(BaseSettingsModel):
    user_level: Annotated[
        UserLevel,
        SettingsField(
            title="User Level",
            example="user",
        ),
    ] = "user"

    studio: Annotated[
        StudioManagementPermissions | None,
        SettingsField(
            title="Studio Permissions",
            description="Permissions for the studio",
        ),
    ] = None

    projects: Annotated[
        dict[str, Permissions] | None,
        SettingsField(
            example={
                "project01": Permissions(),
                "project02": Permissions(),
            },
            title="Projects Permissions",
            description="Permissions for individual projects",
        ),
    ] = None


def build_user_permissions_model(user: UserEntity) -> UserPermissionsModel:
    user_level = "admin" if user.is_admin else "manager" if user.is_manager else "user"

    if user_level != "user":
        return UserPermissionsModel(user_level=user_level)

    default_perms = user.permissions()

    project_perms = {}
    for project_name in user.data.get("accessGroups", {}):
        perms = user.permissions(project_name=project_name)
        project_perms[project_name] = Permissions(**perms.dict())

    return UserPermissionsModel(
        studio=default_perms.studio,
        projects=project_perms,
    )


#
# My permissions
#


@router.get("/me/permissions")
async def get_my_permissions(user: CurrentUser) -> UserPermissionsModel:
    """Return the permissions of the current user.

    The result contains the user's studio permissions
    (taken from the default access groups) and the permissions for each project
    the user has access to.
    """
    return build_user_permissions_model(user)


@router.get("/me/permissions/{project_name}")
async def get_my_project_permissions(
    project_name: ProjectName,
    user: CurrentUser,
) -> Permissions:
    """Return the project permissions of the current user and the given project"""

    if user.is_manager:
        return manager_permissions
    perms = user.permissions(project_name=project_name)
    if perms is None:
        raise ForbiddenException("User does not have access to this project")
    return Permissions(**perms.dict())


#
# Other users' permissions
# Not used in the current version of the frontend. But useful for debugging.
#


@router.get("/{user_name}/permissions")
async def get_user_studio_permissions(
    user: CurrentUser, user_name: UserName
) -> Permissions:
    """Return the studio permissions of the specified user."""

    if not user.is_manager:
        raise ForbiddenException(
            "You do not have permission to view this user's permissions"
        )
    target_user = await UserEntity.load(user_name)
    if target_user.is_manager:
        return manager_permissions
    perms = target_user.permissions()
    if perms is None:
        raise ForbiddenException("User does not have access to this project")
    return Permissions(**perms.dict())


@router.get("/{user_name}/permissions/{project_name}")
async def get_user_project_permissions(
    project_name: ProjectName,
    user_name: UserName,
    user: CurrentUser,
) -> Permissions:
    """Return the project permissions of the specified user and projects"""

    if not user.is_manager:
        raise ForbiddenException(
            "You do not have permission to view this user's permissions"
        )
    target_user = await UserEntity.load(user_name)
    if target_user.is_manager:
        return manager_permissions
    perms = target_user.permissions(project_name=project_name)
    if perms is None:
        raise ForbiddenException("User does not have access to this project")
    return Permissions(**perms.dict())

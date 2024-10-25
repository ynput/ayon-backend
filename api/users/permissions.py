from typing import Annotated, Literal

from ayon_server.access.permissions import Permissions
from ayon_server.api.dependencies import CurrentUser, ProjectName, UserName
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField

from .router import router

manager_permissions = Permissions(project={"enabled": False})


class StudioPermissions(BaseSettingsModel):
    create_project: Annotated[bool, SettingsField(title="Create Project")] = False


class UserPermissionsModel(BaseSettingsModel):
    user_level: Literal["admin", "manager", "user"] = "user"
    studio: Annotated[
        StudioPermissions | None,
        SettingsField(
            title="Studio Permissions", description="Permissions for the studio"
        ),
    ] = None
    projects: Annotated[
        dict[str, Permissions] | None,
        SettingsField(example={"project1": Permissions(project={"enabled": True})}),
    ] = None


def build_user_permissions_model(user: UserEntity) -> UserPermissionsModel:
    user_level = "admin" if user.is_admin else "manager" if user.is_manager else "user"

    if user_level != "user":
        return UserPermissionsModel(user_level=user_level)

    default_perms = user.permissions()
    create_project = (not default_perms.project.enabled) or default_perms.project.create

    project_perms = {}
    for project_name in user.data.get("accessGroups", {}):
        project_perms[project_name] = user.permissions(project_name=project_name)

    return UserPermissionsModel(
        studio=StudioPermissions(
            create_project=create_project,
        ),
        projects=project_perms,
    )


@router.get(
    "/me/permissions",
)
async def get_current_user_permissions(user: CurrentUser) -> UserPermissionsModel:
    return build_user_permissions_model(user)


@router.get("/me/permissions/{project_name}")
async def get_current_user_project_permissions(
    project_name: ProjectName,
    user: CurrentUser,
) -> Permissions:
    if user.is_manager:
        return manager_permissions
    perms = user.permissions(project_name=project_name)
    if perms is None:
        raise ForbiddenException("User does not have access to this project")
    return perms


@router.get("/{user_name}/permissions")
async def get_user_permissions(user: CurrentUser, user_name: UserName) -> Permissions:
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
    return perms


@router.get("/{user_name}/permissions/{project_name}")
async def get_user_project_permissions(
    project_name: ProjectName,
    user_name: UserName,
    user: CurrentUser,
) -> Permissions:
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
    return perms

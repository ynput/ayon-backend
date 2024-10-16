from ayon_server.access.permissions import Permissions
from ayon_server.api.dependencies import CurrentUser, ProjectName, UserName
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException

from .router import router


@router.get("/me/perimissions")
async def get_current_user_permissions(user: CurrentUser):
    perms = user.permissions()
    if perms is None:
        raise ForbiddenException("User does not have access to this project")
    return perms


@router.get("/me/permissions/{project_name}")
async def get_current_user_project_permissions(
    project_name: ProjectName,
    user: CurrentUser,
) -> Permissions:
    perms = user.permissions(project_name=project_name)

    if perms is None:
        raise ForbiddenException("User does not have access to this project")
    return perms


@router.get("/{user_name}/permissions")
async def get_user_permissions(user: CurrentUser, user_name: UserName):
    if not user.is_manager:
        raise ForbiddenException(
            "You do not have permission to view this user's permissions"
        )

    target_user = await UserEntity.load(user_name)
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
    perms = target_user.permissions(project_name=project_name)

    if perms is None:
        raise ForbiddenException("User does not have access to this project")
    return perms

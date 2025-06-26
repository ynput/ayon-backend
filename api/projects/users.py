import copy

from ayon_server.api.dependencies import CurrentUser, ProjectName, UserName
from ayon_server.entities import UserEntity
from ayon_server.lib.postgres import Postgres

from .router import router


@router.get("/projects/{project_name}/users")
async def get_project_users(
    user: CurrentUser,
    project_name: ProjectName,
) -> dict[str, list[str]]:
    """Return a list of users on the project

    This only returns a list of users that have explicitly
    set an access group for the project. It does not include managers
    and admins as they have access to all projects.

    The result is a dictionary where the key is the user's name
    and the value is a list of access groups the user has for the project.

    User invoking this endpoint must have the "project.access" read
    permission for the project.
    """

    user.check_permissions("project.access", project_name)

    query = f"""
        SELECT name, data->'accessGroups'->'{project_name}' as access_groups
        FROM users
        WHERE data->'accessGroups'->'{project_name}' IS NOT NULL
    """

    result: dict[str, list[str]] = {}

    async for row in Postgres.iterate(query):
        result[row["name"]] = row["access_groups"]

    return result


@router.patch("/projects/{project_name}/users/{user_name}")
async def update_project_user(
    user: CurrentUser,
    project_name: ProjectName,
    user_name: UserName,
    access_groups: list[str],
) -> dict[str, list[str]]:
    """Update a user's access groups for a project

    This endpoint is used to update a user's access groups for a project.
    The invoking user must have the "project.access" permission for the project.

    The access groups are a list of strings. The user's access groups
    for the project will be set to this list.

    The result is a dictionary where the key is the user's name
    and the value is a list of access groups the user has for the project.
    """

    user.check_permissions("project.access", project_name, write=True)

    async with Postgres.transaction():
        target_user = await UserEntity.load(user_name, for_update=True)
        target_user_ag = copy.deepcopy(target_user.data.get("accessGroups", {}))
        if not access_groups:
            target_user_ag.pop(project_name, None)
        else:
            target_user_ag[project_name] = access_groups
        target_user.data["accessGroups"] = target_user_ag
        await target_user.save()
    return await get_project_users(user, project_name)

import copy
from collections import defaultdict
from typing import Annotated

from fastapi import Body

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.auth.session import Session
from ayon_server.entities.user import UserEntity
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres

from .router import router

# {project_name: [access_group_name, ...]}
ProjectAccess = dict[str, list[str]]

example = {
    "alice": {
        "MyProject01": ["editor"],
        "MyProject02": ["artist"],
    },
    "bob": {
        "MyProject01": ["artist", "reviewer"],
        "MyProject02": [],
    },
}


@router.post("/access")
async def set_projects_access(
    current_user: CurrentUser,
    payload: Annotated[
        dict[str, ProjectAccess],
        Body(example=example),
    ],
) -> EmptyResponse:
    """Set access for multiple projects

    The payload structure is:
    ```
    {
        userName: {
            projectName: [accessGroupName, ...],
        }
    }
    ```

    To revoke access, set `projectName` to `[]`
    Projects not present in the payload will not be affected

    """

    project_list = await get_project_list()
    all_project_names = [project.name for project in project_list]

    # ensure the user has the necessary permissions
    projects_to_check = set()
    for user_name, project_access in payload.items():
        for project_name in project_access.keys():
            projects_to_check.add(project_name)

    for project_name in projects_to_check:
        current_user.check_permissions("project.access", project_name)

    # Get all active session of the affected users
    sessions = defaultdict(list)
    async for session in Session.list():
        user_name = session.user.name
        if user_name in payload:
            sessions[user_name].append(session.token)

    async with Postgres.transaction():
        for user_name, project_access in payload.items():
            user = await UserEntity.load(user_name, for_update=True)
            access_groups = copy.deepcopy(user.data.get("accessGroups", {}))

            for project_name, project_access_groups in project_access.items():
                if project_name not in all_project_names:
                    continue
                if project_access_groups:
                    access_groups[project_name] = project_access_groups
                else:
                    access_groups.pop(project_name, None)

            ags_to_remove = set()
            for project_name, ags in access_groups.items():
                if not ags:
                    ags_to_remove.add(project_name)
                if project_name not in all_project_names:
                    ags_to_remove.add(project_name)

            for project_name in ags_to_remove:
                access_groups.pop(project_name, None)

            user.data["accessGroups"] = access_groups
            await user.save(run_hooks=False)

            # Update all active sessions of the user
            for token in sessions[user.name]:
                await Session.update(token, user)

    return EmptyResponse()

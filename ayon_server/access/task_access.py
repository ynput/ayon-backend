"""Which tasks a user with restricted read access may see.

With "show sibling tasks" disabled, a task is visible only when the user has read
access to its folder path, or when the read access is "assigned" and the user is
assigned to the task. Shared by the tasks GraphQL resolver and the REST endpoints.
"""

from typing import TYPE_CHECKING

from ayon_server.access.access_groups import AccessGroups
from ayon_server.access.utils import path_to_paths
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres

if TYPE_CHECKING:
    from ayon_server.entities import UserEntity


class FullAccess(Exception):
    pass


async def create_task_acl(
    project_name: str, access_group_names: list[str]
) -> tuple[set[str], bool]:
    """Get the access control list for tasks based on access groups.

    - set of folder paths we have full access to
    - bool indicating if we have 'assigned' access

    raises FullAccess if we have full access to all tasks

    """

    full_access = set()
    assigned_access: bool = False

    for ag_name in access_group_names:
        if (ag_name, project_name) in AccessGroups.access_groups:
            ag_perms = AccessGroups.access_groups[(ag_name, project_name)]
        elif (ag_name, "_") in AccessGroups.access_groups:
            ag_perms = AccessGroups.access_groups[(ag_name, "_")]
        else:
            continue
        read_perms = ag_perms.read
        if not read_perms.enabled:
            # we have an access group that does not restrict read access,
            # so we have full access
            raise FullAccess()
        for acl in read_perms.access_list:
            if acl.access_type == "assigned":
                assigned_access = True
                continue

            if acl.path is None:
                # make linter happy. path is nullable only for 'assigned' type
                continue

            for p in path_to_paths(acl.path, True, True):
                full_access.add(p)

    return full_access, assigned_access


async def ensure_task_read_access(
    user: "UserEntity",
    project_name: str,
    folder_id: str,
    assignees: list[str],
) -> None:
    """Apply the "show sibling tasks" setting to reading a single task.

    Folder access is checked separately (ensure_entity_access); this only
    narrows it down to the tasks the tasks resolver would list.
    """
    if user.is_manager:
        return
    if user.permissions(project_name).advanced.show_sibling_tasks:
        return

    try:
        paths, assigned_access = await create_task_acl(
            project_name,
            user.data.get("accessGroups", {}).get(project_name, []),
        )
    except FullAccess:
        return

    if assigned_access and user.name in assignees:
        return

    if paths:
        res = await Postgres.fetchrow(
            f"""
            SELECT 1 FROM project_{project_name}.hierarchy
            WHERE id = $1 AND path LIKE ANY($2)
            """,
            folder_id,
            [p.strip('"') for p in paths],
        )
        if res:
            return

    raise ForbiddenException("You don't have access to this task")

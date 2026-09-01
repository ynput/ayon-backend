from collections.abc import Iterable
from typing import Any

from ayon_server.config import ayonconfig
from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.enum.base_resolver import BaseEnumResolver
from ayon_server.enum.enum_item import EnumItem
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.auth_utils import AuthUtils
from ayon_server.lib.postgres import Postgres
from ayon_server.models import IconModel
from ayon_server.types import AttributeType

query = """
    SELECT name, attrib, data, active FROM public.users
    ORDER BY COALESCE(attrib->>'fullName', name)
"""


def should_list_user(
    current_user: UserEntity | None,
    context: dict[str, Any],
    udata: dict[str, Any],
    *,
    project_name: str | None,
    skip_if_not_ag: Iterable[str] | None,
    has_all_user_access: bool,
) -> bool:
    """
    Exclude users that the current user has no access to.
    Excluded users won't be returned at all opposed to being returned as hidden
    """
    is_admin = udata.get("isAdmin", False)
    is_manager = udata.get("isManager", False)

    if is_admin or is_manager:
        # we always show admins and managers
        return True

    if not project_name:
        return has_all_user_access

    # now we are in project scope

    ags = udata.get("accessGroups", {}).get(project_name, [])
    if not ags:
        return False

    if not skip_if_not_ag:
        return True

    return bool(set(ags).intersection(set(skip_if_not_ag)))


def should_hide_user(
    current_user: UserEntity | None,
    context: dict[str, Any],
    udata: dict[str, Any],
    *,
    active: bool = True,
    user_pool_ids: list[str] | None = None,
) -> bool:
    """
    Hide users that the current user has acccess to,
    but should be hidden from the list. That allows displaying
    them, but not selecting them.
    """

    if (
        current_user
        and (not current_user.data.get("isSupport", False))
        and udata.get("isSupport", False)
    ):
        # we don't show support users to non-support users
        return True

    if context.get("hide_inactive"):
        if not active:
            return True

        if user_pool_ids and (udata.get("userPool") not in user_pool_ids):
            return True

    return False


class UsersEnumResolver(BaseEnumResolver):
    name = "users"

    async def get_accepted_params(self) -> dict[str, AttributeType]:
        return {
            "project_name": "string",
            "include_teams": "boolean",
            "hide_inactive": "boolean",  # Hide inactive users and users without license
            "hide_users": "boolean",  # Hide all users (when listing teams only)
        }

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        result: list[EnumItem] = []

        project_name = context.get("project_name")
        current_user = context.get("user")

        skip_if_not_ag = None
        has_all_user_access = False

        if not current_user:
            # If there is no current user, we assume this is a system process
            # that has access to all users.
            has_all_user_access = True
        else:
            try:
                current_user.check_permissions("studio.list_all_users")
            except ForbiddenException:
                # normal user without studio-wide access
                if ayonconfig.limit_user_visibility:
                    skip_if_not_ag = current_user.data.get("accessGroups", {}).get(
                        project_name, []
                    )
            else:
                has_all_user_access = True

        if not has_all_user_access:
            if not project_name:
                # Non-managers can only query users within a project
                # they have access to.
                raise ForbiddenException(
                    "You don't have access to studio-wide user list"
                )

            assert current_user is not None  # for mypy
            current_user_ags = current_user.data.get("accessGroups", {}).get(
                project_name, []
            )
            if not current_user_ags:
                raise ForbiddenException("You don't have access to this project")

        user_pool_ids = [
            pool.id for pool in await AuthUtils.get_user_pools() if pool.valid
        ]

        async with Postgres.transaction():
            stmt = await Postgres.prepare(query)
            async for row in stmt.cursor():
                name, attrib, udata, active = row

                if not should_list_user(
                    current_user,
                    context,
                    udata,
                    project_name=project_name,
                    skip_if_not_ag=skip_if_not_ag,
                    has_all_user_access=has_all_user_access,
                ):
                    continue

                item = EnumItem(
                    value=name,
                    label=attrib.get("fullName") or name,
                    group="Users",
                    hidden=should_hide_user(
                        current_user,
                        context,
                        udata,
                        active=active,
                        user_pool_ids=user_pool_ids,
                    ),
                    icon=IconModel(
                        type="url",
                        url=f"/api/users/{name}/avatar",
                    ),
                )
                result.append(item)

        if context.get("include_teams") and context.get("project_name"):
            project = await ProjectEntity.load(context["project_name"])
            for team in project.data.get("teams", []):
                team_name = team.get("name") or "Unnamed Team"
                item = EnumItem(
                    value=f"team:{team_name}",
                    label=team_name,
                    group="Teams",
                    icon=IconModel(
                        type="material-symbols",
                        name="group",
                    ),
                )
                result.append(item)

        return result

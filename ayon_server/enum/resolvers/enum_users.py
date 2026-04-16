from typing import Any

from ayon_server.config import ayonconfig
from ayon_server.enum.base_resolver import BaseEnumResolver
from ayon_server.enum.enum_item import EnumItem
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.models import IconModel

query = """
    SELECT name, attrib, data FROM public.users
    ORDER BY COALESCE(attrib->>'fullName', name)
"""


class UsersEnumResolver(BaseEnumResolver):
    name = "users"

    async def get_accepted_params(self) -> dict[str, type]:
        return {"project_name": str}

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

        def should_show_user(udata: dict[str, Any]) -> bool:
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

        async with Postgres.transaction():
            stmt = await Postgres.prepare(query)
            async for row in stmt.cursor():
                name, attrib, udata = row

                if not should_show_user(udata):
                    continue

                item = EnumItem(
                    value=name,
                    label=attrib.get("fullName") or name,
                    icon=IconModel(
                        type="url",
                        url=f"/api/users/{name}/avatar",
                    ),
                )
                result.append(item)

        return result

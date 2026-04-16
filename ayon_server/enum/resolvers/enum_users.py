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
        if current_user and not current_user.is_manager:
            if not project_name:
                # Non-managers can only query users within a project
                # they have access to.
                raise ForbiddenException("Project name is required for non-admins")

            current_user_ags = current_user.data.get("accessGroups", {}).get(
                project_name, []
            )
            if not current_user_ags:
                raise ForbiddenException("You don't have access to this project")

        skip_if_not_ag = None
        if (
            ayonconfig.limit_user_visibility
            and current_user
            and not current_user.is_manager
        ):
            skip_if_not_ag = current_user.data.get("accessGroups", {}).get(
                project_name, []
            )

        def should_show_user(udata: dict[str, Any]) -> bool:
            is_admin = udata.get("isAdmin", False)
            is_manager = udata.get("isManager", False)

            if is_admin or is_manager:
                return True

            if not current_user:
                return True

            if not project_name:
                return current_user.is_manager

            # now we are in project scope

            ags = udata.get("accessGroups", {}).get(project_name, [])
            if not ags:
                return False

            if current_user.is_manager:
                return True

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

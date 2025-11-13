from typing import Any

from ayon_server.config import ayonconfig
from ayon_server.enum.base_resolver import BaseEnumResolver
from ayon_server.enum.enum_item import EnumItem
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
        if current_user and not current_user.is_manager and not project_name:
            # Non-managers can only query users within a project
            # they have access to.
            return []

        skip_if_not_ag = None
        if ayonconfig.limit_user_visibility and current_user:
            skip_if_not_ag = current_user.data.get("accessGroups", {}).get(
                project_name, []
            )

        async with Postgres.transaction():
            stmt = await Postgres.prepare(query)
            async for row in stmt.cursor():
                name, attrib, udata = row

                is_admin = udata.get("isAdmin", False)
                is_manager = udata.get("isManager", False)

                if not (is_admin or is_manager):
                    ags = udata.get("accessGroups", {}).get(project_name, [])
                    if not ags:
                        continue

                    if skip_if_not_ag is not None:
                        if not set(ags).intersection(set(skip_if_not_ag)):
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

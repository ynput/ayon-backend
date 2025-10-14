from typing import Any

from ayon_server.enum.base_resolver import BaseEnumResolver
from ayon_server.enum.enum_item import EnumItem
from ayon_server.lib.postgres import Postgres
from ayon_server.models.icon_model import IconModel

query = """
    SELECT name, attrib, data FROM public.users
    ORDER BY COALESCE(attrib->>'fullName', name)
"""


class UsersEnumResolver(BaseEnumResolver):
    name = "users"

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        result: list[EnumItem] = []

        project_name = context.get("project_name")
        user = context.get("user")
        if user and not user.is_manager and not project_name:
            # Non-managers can only query users within a project
            # they have access to.
            return []

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

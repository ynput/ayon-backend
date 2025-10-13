from ayon_server.entities import UserEntity
from ayon_server.enum.enum_item import EnumItem
from ayon_server.lib.postgres import Postgres
from ayon_server.models.icon_model import IconModel

query = """
    SELECT name, attrib FROM public.users
    ORDER BY COALESCE(attrib->>'fullName', name)
"""


async def enum_users(
    user: UserEntity | None = None,
    project_name: str | None = None,
) -> list[EnumItem]:
    result: list[EnumItem] = []

    async with Postgres.transaction():
        stmt = await Postgres.prepare(query)
        async for row in stmt.cursor():
            name, attrib = row
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

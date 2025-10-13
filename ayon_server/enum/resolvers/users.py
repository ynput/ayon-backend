from ayon_server.entities import UserEntity
from ayon_server.enum.enum_item import EnumItem


async def enum_users(
    user: UserEntity | None = None,
    project_name: str | None = None,
) -> list[EnumItem]:
    result: list[EnumItem] = []

    return result

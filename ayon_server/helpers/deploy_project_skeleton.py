from typing import Any

from ayon_server.settings.anatomy import Anatomy


async def create_project_skeleton_from_anatomy(
    name: str,
    code: str,
    anatomy: Anatomy,
    *,
    library: bool = False,
    user_name: str | None = None,
    data: dict[str, Any] | None = None,
    assign_users: bool = True,
) -> None:
    pass

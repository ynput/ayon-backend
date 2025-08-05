from typing import Any

from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.exceptions import ForbiddenException


class EntityAccessHelper:
    NO_ACCESS = 0
    READ = 10
    UPDATE = 20
    MANAGE = 30

    @classmethod
    async def check(
        cls,
        user: UserEntity,
        *,
        access: dict[str, Any] | None = None,
        level: int = 0,
        owner: str | None = None,
        project: ProjectEntity | None = None,
        default_open: bool = True,
    ) -> None:
        _ = access, user, level, owner

        if owner and user.name == owner:
            return

        if default_open:
            return

        raise ForbiddenException()

from typing import Any

from ayon_server.entities import ProjectEntity, UserEntity


class EntityAccessHelper:
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
        return

from typing import Any

from ayon_server.entities import UserEntity


class EntityAccessHelper:
    @classmethod
    async def check(
        cls,
        access: dict[str, Any],
        user: UserEntity,
        level: int = 0,
        *,
        owner: str | None = None,
    ) -> None:
        _ = access, user, level, owner
        return

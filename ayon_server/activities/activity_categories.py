from typing import Any

from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.helpers.entity_access import EntityAccessHelper


class ActivityCategories:
    @classmethod
    async def get_activity_categories(cls, project_name: str) -> list[dict[str, Any]]:
        return []

    @classmethod
    async def get_accessible_categories(
        cls,
        user: UserEntity,
        *,
        project_name: str | None = None,
        level: int = EntityAccessHelper.READ,
        project: ProjectEntity | None = None,
    ) -> list[str]:
        return []

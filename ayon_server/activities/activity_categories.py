from typing import Any


class ActivityCategories:
    @classmethod
    async def get_activity_categories(cls, project_name: str) -> list[dict[str, Any]]:
        return []

    @classmethod
    async def get_writable_categories(cls, user: Any, project_name: str) -> list[str]:
        return []

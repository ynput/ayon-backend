from typing import Any

from ayon_server.enum.base_resolver import BaseEnumResolver
from ayon_server.enum.enum_item import EnumItem
from ayon_server.helpers.project_list import normalize_project_name
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.settings.enum import get_primary_anatomy_preset


class FolderTypesEnumResolver(BaseEnumResolver):
    name = "folderTypes"

    async def get_accepted_params(self) -> dict[str, type]:
        return {"project_name": str}

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        project_name = context.get("project_name")
        if not project_name:
            anatomy = await get_primary_anatomy_preset()
            return [
                EnumItem(
                    value=folder_type.name,
                    label=folder_type.name,
                    icon=folder_type.icon,
                    color=folder_type.color,
                )
                for folder_type in anatomy.folder_types
            ]

        project_name = await normalize_project_name(project_name)
        result: list[EnumItem] = []
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            stmt = await Postgres.prepare(
                "SELECT name, data FROM folder_types ORDER BY position"
            )
            async for row in stmt.cursor():
                result.append(
                    EnumItem(
                        value=row["name"],
                        label=row["name"],
                        icon=row["data"].get("icon"),
                        color=row["data"].get("color"),
                    )
                )
        return result

    async def create_item(
        self,
        item: EnumItem,
        project_name: str | None = None,
        **kwargs,
    ) -> None:
        _ = kwargs  # Unused for now, but allows for future extensibility

        if not project_name:
            raise ValueError("Missing project name in item data")

        project_name = await normalize_project_name(project_name)
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            await Postgres.execute(
                """
                INSERT INTO folder_types (name, data, position)
                VALUES (
                    $1,
                    $2,
                    (SELECT COALESCE(MAX(position), 0) + 1 FROM folder_types))
                """,
                item.value,
                {
                    "icon": item.icon or "folder",
                    "color": item.color or "#808080",
                    "name": item.value,
                },
            )
        await Redis.delete("project-anatomy", project_name)


class TaskTypesEnumResolver(BaseEnumResolver):
    name = "taskTypes"

    async def get_accepted_params(self) -> dict[str, type]:
        return {"project_name": str}

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        project_name = context.get("project_name")
        if not project_name:
            anatomy = await get_primary_anatomy_preset()
            return [
                EnumItem(
                    value=task_type.name,
                    label=task_type.name,
                    icon=task_type.icon,
                    color=task_type.color,
                )
                for task_type in anatomy.task_types
            ]

        project_name = await normalize_project_name(project_name)
        result: list[EnumItem] = []
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            stmt = await Postgres.prepare(
                "SELECT name, data FROM task_types ORDER BY position"
            )
            async for row in stmt.cursor():
                result.append(
                    EnumItem(
                        value=row["name"],
                        label=row["name"],
                        icon=row["data"].get("icon"),
                        color=row["data"].get("color"),
                    )
                )
        return result

    async def create_item(
        self,
        item: EnumItem,
        project_name: str | None = None,
        **kwargs,
    ) -> None:
        if not project_name:
            raise ValueError("Missing project name in item data")

        project_name = await normalize_project_name(project_name)
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            await Postgres.execute(
                """
                INSERT INTO task_types (name, data, position)
                VALUES ($1, $2, (SELECT COALESCE(MAX(position), 0) + 1 FROM task_types))
                """,
                item.value,
                {
                    "icon": item.icon or "task",
                    "color": item.color or "#808080",
                    "name": item.value,
                },
            )
        await Redis.delete("project-anatomy", project_name)


class StatusesEnumResolver(BaseEnumResolver):
    name = "statuses"

    async def get_accepted_params(self) -> dict[str, type]:
        return {"project_name": str}

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        project_name = context.get("project_name")
        if not project_name:
            anatomy = await get_primary_anatomy_preset()
            return [
                EnumItem(
                    value=status.name,
                    label=status.name,
                    icon=status.icon,
                    color=status.color,
                )
                for status in anatomy.statuses
            ]

        project_name = await normalize_project_name(project_name)
        result: list[EnumItem] = []
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            stmt = await Postgres.prepare(
                "SELECT name, data FROM statuses ORDER BY position"
            )
            async for row in stmt.cursor():
                result.append(
                    EnumItem(
                        value=row["name"],
                        label=row["name"],
                        icon=row["data"].get("icon"),
                        color=row["data"].get("color"),
                    )
                )
        return result

    async def create_item(
        self,
        item: EnumItem,
        project_name: str | None = None,
        **kwargs,
    ) -> None:
        if not project_name:
            raise ValueError("Missing project name in item data")

        project_name = await normalize_project_name(project_name)
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            await Postgres.execute(
                """
                INSERT INTO statuses (name, data, position)
                VALUES ($1, $2, (SELECT COALESCE(MAX(position), 0) + 1 FROM statuses))
                """,
                item.value,
                {
                    "icon": item.icon or "check_circle",
                    "color": item.color or "#808080",
                    "name": item.value,
                },
            )
        await Redis.delete("project-anatomy", project_name)


class TagsEnumResolver(BaseEnumResolver):
    name = "tags"

    async def get_accepted_params(self) -> dict[str, type]:
        return {"project_name": str}

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        project_name = context.get("project_name")
        if not project_name:
            anatomy = await get_primary_anatomy_preset()
            return [
                EnumItem(
                    value=tag.name,
                    label=tag.name,
                    color=tag.color,
                )
                for tag in anatomy.tags
            ]

        project_name = await normalize_project_name(project_name)
        result: list[EnumItem] = []
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            stmt = await Postgres.prepare(
                "SELECT name, data FROM tags ORDER BY position"
            )
            async for row in stmt.cursor():
                result.append(
                    EnumItem(
                        value=row["name"],
                        label=row["name"],
                        color=row["data"].get("color"),
                    )
                )
        return result

    async def create_item(
        self,
        item: EnumItem,
        project_name: str | None = None,
        **kwargs,
    ) -> None:
        if not project_name:
            raise ValueError("Missing project name in item data")

        project_name = await normalize_project_name(project_name)
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            await Postgres.execute(
                """
                INSERT INTO tags (name, data, position)
                VALUES ($1, $2, (SELECT COALESCE(MAX(position), 0) + 1 FROM tags))
                """,
                item.value,
                {"color": item.color or "#808080", "name": item.value},
            )
        await Redis.delete("project-anatomy", project_name)

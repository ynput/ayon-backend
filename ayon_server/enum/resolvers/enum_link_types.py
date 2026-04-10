from typing import Any

from ayon_server.enum.base_resolver import BaseEnumResolver
from ayon_server.enum.enum_item import EnumItem
from ayon_server.helpers.anatomy import get_project_anatomy
from ayon_server.helpers.project_list import normalize_project_name
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.settings.anatomy import Anatomy
from ayon_server.settings.anatomy.link_types import LinkType


def link_type_to_enum_item(link_type: LinkType) -> EnumItem:
    label = link_type.link_type.capitalize()
    label += f" ({link_type.input_type} -> {link_type.output_type})"
    return EnumItem(
        value=link_type.name,
        label=label,
        color=link_type.color,
    )


async def _resolve_link_types_studio() -> list[EnumItem]:
    result: list[EnumItem] = []
    query = "SELECT data FROM anatomy_presets WHERE is_primary"
    res = await Postgres.fetchrow(query)
    if res:
        anatomy = Anatomy(**res["data"])
    else:
        anatomy = Anatomy()
    for lt in anatomy.link_types:
        result.append(link_type_to_enum_item(lt))
    return result


async def _resolve_link_types_project(project_name: str) -> list[EnumItem]:
    anatomy = await get_project_anatomy(project_name)
    result: list[EnumItem] = []
    for lt in anatomy.link_types:
        result.append(link_type_to_enum_item(lt))
    return result


class LinkTypesEnumResolver(BaseEnumResolver):
    name = "linkTypes"

    async def get_accepted_params(self) -> dict[str, type]:
        return {"project_name": str}

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        project_name = context.get("project_name")
        if not project_name or project_name == "_":
            return await _resolve_link_types_studio()
        return await _resolve_link_types_project(project_name)

    async def create_item(
        self,
        item: EnumItem,
        project_name: str | None = None,
        **kwargs,
    ) -> None:
        if not project_name or project_name == "_":
            raise ValueError("Link types require a project name")

        project_name = await normalize_project_name(project_name)
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            link_type_params = kwargs["link_type_params"]
            input_type = link_type_params.get("input_type")
            output_type = link_type_params.get("output_type")
            link_type = link_type_params.get("link_type", item.value)
            style = link_type_params.get("style", "solid")

            if not all([input_type, output_type, link_type]):
                raise ValueError(
                    "Missing required parameters: input_type, output_type, link_type"
                )
            await Postgres.execute(
                """
                INSERT INTO link_types
                    (name, input_type, output_type, link_type, data)
                VALUES ($1, $2, $3, $4, $5)
                """,
                item.value,
                input_type,
                output_type,
                link_type,
                {"color": item.color or "#808080", "style": style},
            )
        await Redis.delete("project-anatomy", project_name)
        await Redis.delete("project-data", project_name)
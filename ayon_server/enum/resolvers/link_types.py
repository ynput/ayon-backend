from typing import Any

from ayon_server.enum.base_resolver import BaseEnumResolver
from ayon_server.enum.enum_item import EnumItem
from ayon_server.helpers.anatomy import get_project_anatomy
from ayon_server.lib.postgres import Postgres
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

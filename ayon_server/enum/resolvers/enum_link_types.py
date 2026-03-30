from typing import Any
import json

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

    async def create_item(
        self,
        item: EnumItem,
        project_name: str | None = None,
        **kwargs
    ) -> str:
        if not project_name or project_name == "_":
            raise ValueError("Link types require a project name")

        from ayon_server.settings.anatomy import Anatomy

        # Get current anatomy
        anatomy = await get_project_anatomy(project_name)

        # Check if item with same name already exists
        for lt in anatomy.link_types:
            if lt.name == item.value:
                return item.value

        # Create new link type
        new_link_type = {
            "name": item.value,
            "link_type": item.value.lower().replace(" ", "_"),
            "input_type": "folder",
            "output_type": "folder",
            "color": item.color or "#FFFFFF",
        }

        # Add to anatomy link_types
        link_types_list = [lt.model_dump() for lt in anatomy.link_types]
        link_types_list.append(new_link_type)

        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            await Postgres.execute(
                """
                UPDATE project_anatomy
                SET data = jsonb_set(data, '{link_types}', to_jsonb($1::jsonb))
                WHERE name = $2
                """,
                json.dumps(link_types_list),
                project_name,
            )

        return item.value

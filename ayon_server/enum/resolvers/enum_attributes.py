from typing import Any

from ayon_server.entities.core.attrib import attribute_library
from ayon_server.enum.base_resolver import BaseEnumResolver
from ayon_server.enum.enum_item import EnumItem
from ayon_server.exceptions import BadRequestException


class AttributeEnumResolver(BaseEnumResolver):
    name = "attrib"

    async def get_accepted_params(self) -> dict[str, type]:
        return {"project_name": str, "name": str}

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        key = context.get("name")
        if not key:
            raise BadRequestException("Missing attribute name")

        try:
            attrib = attribute_library.by_name(key)
        except KeyError:
            raise BadRequestException(f"Unknown attribute '{key}'")

        attr_enum = attrib.get("enum")
        if not attr_enum:
            return []

        result: list[EnumItem] = []
        for enum_item in attr_enum:
            result.append(
                EnumItem(
                    value=enum_item["value"],
                    label=enum_item.get("label", enum_item["value"]),
                    icon=enum_item.get("icon"),
                    color=enum_item.get("color"),
                )
            )

        return result

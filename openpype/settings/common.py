import re

from typing import Any
from pydantic import BaseModel

from openpype.utils import json_loads, json_dumps

pattern = re.compile(r"(?<!^)(?=[A-Z])")


class BaseSettingsModel(BaseModel):
    _isGroup: bool = False
    _title: str = None
    _layout: str = None

    class Config:
        underscore_attrs_are_private = True
        allow_population_by_field_name = True
        json_loads = json_loads
        json_dumps = json_dumps

        @staticmethod
        def schema_extra(
            schema: dict[str, Any],
            model: type["BaseSettingsModel"],
        ) -> None:
            is_group = model.__private_attributes__["_isGroup"].default
            schema["isgroup"] = is_group
            if "title" in schema:
                del schema["title"]

            for attr in ["title", "layout"]:
                if pattr := model.__private_attributes__.get(f"_{attr}"):
                    if pattr.default is not None:
                        schema[attr] = pattr.default

            for name, prop in schema.get("properties", {}).items():
                for key in [*prop.keys()]:
                    if key in ["enum_resolver"]:
                        del prop[key]

                if field := model.__fields__.get(name):
                    if enum_resolver := field.field_info.extra.get("enum_resolver"):
                        prop["enum"] = enum_resolver()

                    if section := field.field_info.extra.get("section"):
                        prop["section"] = section

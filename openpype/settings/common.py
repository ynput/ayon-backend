import re
from typing import Any, Iterable

from nxtools import slugify
from pydantic import BaseModel

from openpype.utils import json_dumps, json_loads

pattern = re.compile(r"(?<!^)(?=[A-Z])")


class BaseSettingsModel(BaseModel):
    _isGroup: bool = False
    _title: str | None = None
    _layout: str | None = None

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
                    if key in ["enum_resolver", "widget"]:
                        del prop[key]

                if field := model.__fields__.get(name):
                    if enum_resolver := field.field_info.extra.get("enum_resolver"):
                        prop["enum"] = enum_resolver()

                    if section := field.field_info.extra.get("section"):
                        prop["section"] = section

                    if widget := field.field_info.extra.get("widget"):
                        prop["widget"] = widget

                    if tags := field.field_info.extra.get("tags"):
                        prop["tags"] = tags


def normalize_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Name must not be empty")
    components = slugify(name).split("-")
    return f"{components[0]}{''.join(x.title() for x in components[1:])}"


def ensure_unique_names(objects: Iterable[Any]) -> None:
    names = []
    for obj in objects:
        if not hasattr(obj, "name"):
            raise ValueError("Object without name provided")
        if obj.name not in names:
            names.append(obj.name)
        else:
            raise ValueError(f"Duplicate name {obj.name}]")

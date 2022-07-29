import re
import inspect
import collections
from typing import Any, Iterable

from nxtools import slugify
from pydantic import BaseModel

from openpype.utils import json_dumps, json_loads, run_blocking_coro

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
        def schema_extra_off(
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
                        if inspect.iscoroutinefunction(enum_resolver):
                            result = run_blocking_coro(enum_resolver)
                            prop["enum"] = result
                        else:
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


async def postprocess_settings_schema(
    schema: dict[str, Any],
    model: type["BaseSettingsModel"],
    is_top_level: bool = True,
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
                if inspect.iscoroutinefunction(enum_resolver):
                    enum = await enum_resolver()
                else:
                    enum = enum_resolver()

                if prop.get("items"):
                    prop["items"]["enum"] = enum
                else:
                    prop["enum"] = enum
                prop["uniqueItems"] = True

            if section := field.field_info.extra.get("section"):
                prop["section"] = section

            if widget := field.field_info.extra.get("widget"):
                prop["widget"] = widget

            if tags := field.field_info.extra.get("tags"):
                prop["tags"] = tags

    if not is_top_level:
        return

    submodels = {}
    submodels_deque = collections.deque()
    submodels_deque.append(model)
    while submodels_deque:
        parent = submodels_deque.popleft()

        if not inspect.isclass(parent):
            continue

        if parent.__name__ in submodels:
            continue

        if not issubclass(parent, BaseSettingsModel):
            continue

        submodels[parent.__name__] = parent

        for field_name, field in parent.__fields__.items():
            submodels_deque.append(field.type_)
            for sub_field in field.sub_fields or []:
                submodels_deque.append(sub_field.type_)

    for definition_name, definition in schema.get("definitions", {}).items():
        if definition_name not in submodels:
            continue
        await postprocess_settings_schema(
            definition, submodels[definition_name], is_top_level=False
        )

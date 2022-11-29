import collections
import inspect
import re
from typing import Any, Deque, Iterable, Type

from nxtools import logging, slugify
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


async def process_enum(enum_resolver) -> tuple[list[str], dict[str, str]]:
    if inspect.iscoroutinefunction(enum_resolver):
        enum = await enum_resolver()
    else:
        enum = enum_resolver()

    enum_values = []
    enum_labels = {}
    if type(enum) is list:
        for item in enum:
            if type(item) is str:
                enum_values.append(item)
            elif type(item) is dict:
                if "value" not in item or "label" not in item:
                    logging.warning(f"Invalid enumerator item: {item}")
                    continue
                enum_values.append(item["value"])
                enum_labels[item["value"]] = item["label"]
    return enum_values, enum_labels


async def postprocess_settings_schema(  # noqa
    schema: dict[str, Any],
    model: type["BaseSettingsModel"],
    is_top_level: bool = True,
) -> None:
    """Post-process exported JSON schema.

    Apply custom attributes to the settings schema.
    That includes layout, custom widgets, enumerators and
    grouping.

    We use this instead of pydantic schema_extra classmethod,
    because we need to support async functions passed to
    enum_resolver argument.

    It is called (and only used) in .../schema requests for
    addon settings and anatomy presets.
    """

    is_group = model.__private_attributes__["_isGroup"].default
    schema["isgroup"] = is_group
    if "title" in schema:
        del schema["title"]

    for attr in ("title", "layout", "dependencies"):
        if pattr := model.__private_attributes__.get(f"_{attr}"):
            if pattr.default is not None:
                schema[attr] = pattr.default

    for name, prop in schema.get("properties", {}).items():
        for key in tuple(prop.keys()):
            if key in ("enum_resolver", "widget"):
                del prop[key]

        if field := model.__fields__.get(name):
            if enum_resolver := field.field_info.extra.get("enum_resolver"):
                enum_values, enum_labels = await process_enum(enum_resolver)
                if prop.get("items"):
                    prop["items"]["enum"] = enum_values
                else:
                    prop["enum"] = enum_values
                if enum_labels:
                    prop["enumLabels"] = enum_labels
                prop["uniqueItems"] = True

            for extra_field_name in (
                "section",
                "widget",
                "layout",
                "scope",
                "tags",
                "placeholder",
                "conditionalEnum",
            ):
                if extra_field := field.field_info.extra.get(extra_field_name):
                    prop[extra_field_name] = extra_field

    if not is_top_level:
        return

    submodels: dict[str, Type[BaseSettingsModel]] = {}
    submodels_deque: Deque[Type[BaseSettingsModel]] = collections.deque()
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

import collections
import inspect
import re
from typing import Any, Deque, Type

from nxtools import logging
from pydantic import BaseModel

from ayon_server.entities.models.generator import EnumFieldDefinition
from ayon_server.exceptions import AyonException
from ayon_server.types import camelize
from ayon_server.utils import json_dumps, json_loads

pattern = re.compile(r"(?<!^)(?=[A-Z])")


class BaseSettingsModel(BaseModel):
    _isGroup: bool = False
    _title: str | None = None
    _layout: str | None = None
    _required: bool = False

    class Config:
        underscore_attrs_are_private = True
        allow_population_by_field_name = True
        json_loads = json_loads
        json_dumps = json_dumps


async def process_enum(
    enum_resolver,
    context: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, str]]:

    if context is None:
        context = {}

    resolver_args = inspect.getfullargspec(enum_resolver).args
    available_keys = list(context.keys())
    for key in available_keys:
        if key not in resolver_args:
            del context[key]

    if inspect.iscoroutinefunction(enum_resolver):
        enum = await enum_resolver(**context)
    else:
        enum = enum_resolver(**context)

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
    context: dict[str, Any] | None = None,
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

    if context is None:
        context = {}

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
            if key in ("enum_resolver", "required_items"):
                del prop[key]

        if field := model.__fields__.get(name):
            enum_values = []
            enum_labels = {}
            is_enum = False
            if enum := field.field_info.extra.get("enum"):
                is_enum = True
                for item in enum:
                    if isinstance(item, EnumFieldDefinition):
                        enum_values.append(item.value)
                        enum_labels[item.value] = item.label
                    elif type(item) is str:
                        enum_values.append(item)
                    elif type(item) is dict:
                        if "value" not in item or "label" not in item:
                            logging.warning(f"Invalid enumerator item: {item}")
                            continue
                        enum_values.append(item["value"])
                        enum_labels[item["value"]] = item["label"]

            elif enum_resolver := field.field_info.extra.get("enum_resolver"):
                is_enum = True
                try:
                    enum_values, enum_labels = await process_enum(
                        enum_resolver, context
                    )
                except AyonException as e:
                    prop["placeholder"] = e.detail
                    prop["disabled"] = True

            if is_enum:
                if prop.get("items"):
                    prop["items"]["enum"] = enum_values
                else:
                    prop["enum"] = enum_values
                if enum_labels:
                    prop["enumLabels"] = enum_labels
                prop["uniqueItems"] = True

            scope = field.field_info.extra.get("scope")
            if scope is None or (type(scope) != list):
                prop["scope"] = ["project", "studio"]
            else:
                # TODO assert scope is valid (contains 'project', 'studio' and/or 'local')
                prop["scope"] = scope

            for extra_field_name in (
                "section",
                "widget",
                "layout",
                "tags",
                "placeholder",
                "required_items",
                "conditional_enum",
                "conditionalEnum",
            ):
                if extra_field := field.field_info.extra.get(extra_field_name):
                    if not camelize(extra_field_name) in prop:
                        prop[camelize(extra_field_name)] = extra_field

            # Support for VERY CUSTOM widgets, which would be otherwise
            # redered as arrays or objects.
            if inspect.isclass(field.type_):
                match field.type_.__name__:
                    case "ColorRGB_hex":
                        prop["type"] = "string"
                        prop["widget"] = "color"
                        prop["colorFormat"] = "hex"
                        prop["colorAlpha"] = False
                    case "ColorRGBA_hex":
                        prop["type"] = "string"
                        prop["widget"] = "color"
                        prop["colorFormat"] = "hex"
                        prop["colorAlpha"] = True
                    case "ColorRGB_float":
                        prop["type"] = "string"
                        prop["widget"] = "color"
                        prop["colorFormat"] = "float"
                        prop["colorAlpha"] = False
                    case "ColorRGBA_float":
                        prop["type"] = "string"
                        prop["widget"] = "color"
                        prop["colorFormat"] = "float"
                        prop["colorAlpha"] = True
                    case "ColorRGB_uint8":
                        prop["type"] = "string"
                        prop["widget"] = "color"
                        prop["colorFormat"] = "uint8"
                        prop["colorAlpha"] = False
                    case "ColorRGBA_uint8":
                        prop["type"] = "string"
                        prop["widget"] = "color"
                        prop["colorFormat"] = "uint8"
                        prop["colorAlpha"] = True

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

        try:
            if not issubclass(parent, BaseSettingsModel):
                continue
        except TypeError:
            # This happens when parent is not a class
            # but a weird field such as Tuple[...]
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
            definition,
            submodels[definition_name],
            is_top_level=False,
            context=context,
        )

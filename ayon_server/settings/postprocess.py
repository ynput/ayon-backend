import collections
import functools
import inspect
from typing import Any

from ayon_server.enum.enum_item import EnumItem
from ayon_server.exceptions import AyonException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.settings.common import BaseSettingsModel
from ayon_server.types import SimpleValue, camelize


def populate_schema_defaults(
    schema: dict[str, Any],
    model: type[BaseSettingsModel],
) -> None:
    definitions = {
        **schema.get("$defs", {}),
        **schema.get("definitions", {}),
    }
    missing = object()

    def resolve(node: dict[str, Any]) -> dict[str, Any]:
        if ref := node.get("$ref"):
            definition_name = ref.rsplit("/", 1)[-1]
            return definitions.get(definition_name, node)
        return node

    def serialize(value: Any) -> Any:
        if isinstance(value, BaseSettingsModel):
            return value.dict()
        if isinstance(value, list):
            return [serialize(item) for item in value]
        if isinstance(value, dict):
            return {key: serialize(item) for key, item in value.items()}
        return value

    def is_settings_model(value: Any) -> bool:
        try:
            return inspect.isclass(value) and issubclass(value, BaseSettingsModel)
        except TypeError:
            return False

    def get_child_model(field: Any) -> type[BaseSettingsModel] | None:
        candidates = [field.type_]
        candidates.extend(sub_field.type_ for sub_field in field.sub_fields or [])
        for candidate in candidates:
            if is_settings_model(candidate):
                return candidate
        return None

    def build_model_defaults(
        current_model: type[BaseSettingsModel],
        stack: set[type[BaseSettingsModel]] | None = None,
    ) -> Any:
        stack = stack or set()
        if current_model in stack:
            return missing

        defaults = {}
        next_stack = {*stack, current_model}
        for field_name, field in current_model.__fields__.items():
            default = get_field_default(field, next_stack)
            if default is not missing:
                defaults[field_name] = default
        return defaults or missing

    def get_field_default(
        field: Any,
        stack: set[type[BaseSettingsModel]] | None = None,
    ) -> Any:
        if field.default_factory is not None:
            if is_settings_model(field.default_factory):
                return build_model_defaults(field.default_factory, stack)
            return serialize(field.default_factory())
        if not field.required:
            return serialize(field.default)
        return missing

    def populate(node: dict[str, Any], current_model: type[BaseSettingsModel]) -> None:
        all_of = node.get("allOf")
        if isinstance(all_of, list):
            for sub_schema in all_of:
                if isinstance(sub_schema, dict):
                    populate(sub_schema, current_model)

        resolved = resolve(node)
        if resolved is not node:
            node = resolved

        for name, field in current_model.__fields__.items():
            child_schema = node.get("properties", {}).get(name)
            if child_schema is None:
                continue

            if "default" not in child_schema:
                default = get_field_default(field)
                if default is not missing:
                    child_schema["default"] = default

            child_model = get_child_model(field)
            if child_model is not None:
                nested_schema = child_schema
                if isinstance(child_schema.get("items"), dict):
                    nested_schema = child_schema["items"]
                populate(nested_schema, child_model)

    populate(schema, model)


async def get_attrib_enum(
    name: str,
) -> tuple[list[SimpleValue], dict[SimpleValue, str]]:
    enum_values = []
    enum_labels = {}

    res = await Postgres.fetch("SELECT data FROM public.attributes WHERE name=$1", name)
    if res:
        for item in res[0]["data"].get("enum", []):
            enum_values.append(item["value"])
            enum_labels[item["value"]] = item["label"]

    return enum_values, enum_labels


async def process_enum(
    enum_resolver,
    context: dict[str, Any] | None = None,
) -> tuple[list[SimpleValue], dict[SimpleValue, str]]:
    if context is None:
        context = {}

    # enum_resolver could use partial for passing arguments in
    partial_kwargs = {}
    if isinstance(enum_resolver, functools.partial):
        partial_kwargs = enum_resolver.keywords
        enum_resolver = enum_resolver.func

    resolver_args = inspect.getfullargspec(enum_resolver).args

    ctx_data = {}
    for key in resolver_args:
        if key in context:
            ctx_data[key] = context[key]
        elif key in partial_kwargs:
            ctx_data[key] = partial_kwargs[key]
        else:
            ctx_data[key] = None

    if inspect.iscoroutinefunction(enum_resolver):
        enum = await enum_resolver(**ctx_data)
    else:
        enum = enum_resolver(**ctx_data)

    enum_values: list[SimpleValue] = []
    enum_labels: dict[SimpleValue, str] = {}
    if not isinstance(enum, list):
        return enum_values, enum_labels
    for item in enum:
        if isinstance(item, str):
            enum_values.append(item)
        elif isinstance(item, EnumItem):
            enum_values.append(item.value)
            enum_labels[item.value] = item.label
        elif isinstance(item, dict):
            if "value" not in item or "label" not in item:
                logger.warning(f"Invalid enumerator item: {item}")
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
            enum_values: list[SimpleValue] = []
            enum_labels: dict[SimpleValue, str] = {}
            is_enum = False
            if enum := field.field_info.extra.get("enum"):
                is_enum = True

                if field.field_info.extra.get("_attrib_enum"):
                    enum_values, enum_labels = await get_attrib_enum(name)
                else:
                    for item in enum:
                        if isinstance(item, EnumItem):
                            enum_values.append(item.value)
                            enum_labels[item.value] = item.label
                        elif isinstance(item, str):
                            enum_values.append(item)
                        elif isinstance(item, dict):
                            if "value" not in item or "label" not in item:
                                logger.warning(f"Invalid enumerator item: {item}")
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
                if "items" in prop:
                    # props.items.enum is for multiselect
                    prop["items"] = {"type": "string"}
                    prop["items"]["enum"] = enum_values
                    prop.pop("enum", None)
                    prop["uniqueItems"] = True
                else:
                    # while props.enum is for single-select
                    prop["enum"] = enum_values

                # enum labels are our own, shared by items.enum and enum,
                # so we put it to the schema top level
                if enum_labels:
                    prop["enumLabels"] = enum_labels

            scope = field.field_info.extra.get("scope")
            if scope is None or (not isinstance(scope, list)):
                prop["scope"] = ["project", "studio"]
            else:
                # TODO assert scope is valid ('project', 'studio' and/or 'site')
                prop["scope"] = scope

            for extra_field_name in (
                "section",
                "widget",
                "layout",
                "tags",
                "placeholder",
                "required_items",
                "conditional_enum",
            ):
                if extra_field := field.field_info.extra.get(extra_field_name):
                    if camelize(extra_field_name) not in prop:
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

    submodels: dict[str, type[BaseSettingsModel]] = {}
    submodels_deque: collections.deque[type[BaseSettingsModel]] = collections.deque()
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

        for _field_name, field in parent.__fields__.items():
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

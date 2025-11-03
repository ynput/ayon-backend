import inspect
import re
from collections.abc import Callable
from types import GenericAlias
from typing import Annotated, Any, get_args, get_origin

from pydantic import BaseModel, ValidationError, parse_obj_as

from ayon_server.logging import logger
from ayon_server.utils import json_dumps, json_loads  # , json_print

pattern = re.compile(r"(?<!^)(?=[A-Z])")


class BaseSettingsModel(BaseModel):
    _isGroup: bool = False
    _title: str | None = None
    _layout: str | None = None
    _required: bool = False
    _has_studio_overrides: bool | None = None
    _has_project_overrides: bool | None = None
    _has_site_overrides: bool | None = None

    class Config:
        underscore_attrs_are_private = True
        allow_population_by_field_name = True
        json_loads = json_loads
        json_dumps = json_dumps


def unwrap_annotated(tp) -> tuple[Any, list[Any] | None]:
    if get_origin(tp) is Annotated:
        actual_type, *metadata = get_args(tp)
        return actual_type, metadata
    return tp, None


def migrate_settings_overrides(
    old_data: dict[str, Any],
    new_model_class: type[BaseSettingsModel],
    defaults: dict[str, Any],
    custom_conversions: dict[str, Callable[[Any], Any]] = {},
    parent_key: str = "",
) -> dict[str, Any]:
    """Migrate settings overrides from old data to new model class."""

    new_data: dict[str, Any] = {}

    if get_origin(new_model_class) is Annotated:
        args = get_args(new_model_class)
        new_model_class = args[0] if args else new_model_class

    for key, value in old_data.items():
        if key in new_model_class.__fields__:
            # Construct the key path for nested fields
            key_path = f"{parent_key}.{key}" if parent_key else key
            field_type = new_model_class.__fields__[key]

            outer_type, _ = unwrap_annotated(field_type.outer_type_)

            if inspect.isclass(field_type.type_) and issubclass(
                field_type.type_, BaseSettingsModel
            ):
                if (
                    isinstance(outer_type, GenericAlias)
                    and outer_type.__origin__ == list
                    and isinstance(value, list)
                ):
                    new_data[key] = [
                        migrate_settings_overrides(
                            v,
                            outer_type.__args__[0],
                            {},
                            custom_conversions,
                            key_path,
                        )
                        for v in value
                    ]

                elif isinstance(value, dict):
                    # TODO: ensure that the field is indeed a submodel
                    # it should, but we should check

                    new_data[key] = migrate_settings_overrides(
                        value,
                        outer_type,
                        defaults.get(key, {}),
                        custom_conversions,
                        key_path,
                    )
                else:
                    sval = str(value)[:70]
                    logger.warning(f"Unsupported type for {key_path} model: {sval}")
            else:
                try:
                    validated_value = parse_obj_as(outer_type, value)
                    new_data[key] = validated_value
                except ValidationError:
                    logger.warning(f"Failed to validate {key} with value {value}")
                    # Skip incompatible fields
                    continue
        else:
            logger.warning(f"Skipping unknown key: {key}")

    # if not parent_key:
    #     json_print(new_data, "New data")

    return new_data

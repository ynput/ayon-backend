import inspect
import re
from typing import Any, Callable, Type

from nxtools import logging
from pydantic import BaseModel, ValidationError, parse_obj_as

from ayon_server.utils import json_dumps, json_loads

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


def migrate_settings(
    old_data: dict[str, Any],
    new_model_class: Type[BaseSettingsModel],
    defaults: dict[str, Any],
    custom_conversions: dict[str, Callable[[Any], Any]] = {},
    parent_key: str = "",
) -> Any:
    new_instance_data = {}
    for field_name, field_type in new_model_class.__fields__.items():
        # Construct the key path for nested fields
        key_path = f"{parent_key}.{field_name}" if parent_key else field_name
        if field_name in old_data:
            old_value = old_data[field_name]
            # Check if there's a custom conversion for this field
            if key_path in custom_conversions:
                new_instance_data[field_name] = custom_conversions[key_path](old_value)
            elif (key := key_path.split(".")[-1]) in custom_conversions:
                new_instance_data[field_name] = custom_conversions[key](old_value)
            elif inspect.isclass(field_type.type_) and issubclass(
                field_type.type_, BaseSettingsModel
            ):
                # Recurse nested models or lists of models
                if isinstance(old_value, list):
                    new_instance_data[field_name] = [
                        migrate_settings(
                            old_value,
                            field_type.type_,
                            defaults.get(field_name, []),
                            custom_conversions,
                            key_path,
                        )
                        for old_value in old_value
                    ]
                elif isinstance(old_value, dict):
                    new_instance_data[field_name] = migrate_settings(
                        old_value,
                        field_type.outer_type_,
                        defaults.get(field_name, {}),
                        custom_conversions,
                        key_path,
                    )
                else:
                    logging.warning(
                        f"Unsupported type for {key_path} model: {old_value}"
                    )
            else:
                try:
                    validated_value = parse_obj_as(field_type.outer_type_, old_value)
                    new_instance_data[field_name] = validated_value
                except ValidationError:
                    logging.warning(
                        f"Failed to validate {field_name} with value {old_value}"
                    )
                    # Skip incompatible fields
                    continue
        else:
            if field_name in defaults:
                new_instance_data[field_name] = defaults.get(field_name, None)

    return new_model_class.parse_obj(new_instance_data)

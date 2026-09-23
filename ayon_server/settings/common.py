import copy
import inspect
import re
from collections.abc import Callable
from typing import Annotated, Any, Literal, get_args, get_origin

from pydantic import (
    BaseModel,
    ConfigDict,
    TypeAdapter,
    ValidationError,
    model_validator,
)
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode

from ayon_server.logging import logger
from ayon_server.models.field_info import V1ModelField, get_inner_type, strip_optional
from ayon_server.models.metaclass import AyonModelMetaclass, coerce_v1_input
from ayon_server.settings.json_schema import REF_TEMPLATE, SettingsJsonSchemaGenerator

pattern = re.compile(r"(?<!^)(?=[A-Z])")


class _V1FieldsDescriptor:
    """Pydantic 1 style `__fields__` (used by addons)"""

    def __get__(self, obj: Any, owner: type[BaseModel]) -> dict[str, V1ModelField]:
        return {
            name: V1ModelField(name, field_info)
            for name, field_info in owner.model_fields.items()
        }


class BaseSettingsModel(BaseModel, metaclass=AyonModelMetaclass):
    _isGroup: bool = False
    _title: str | None = None
    _layout: str | None = None
    _required: bool = False
    _has_studio_overrides: bool | None = None
    _has_project_overrides: bool | None = None
    _has_site_overrides: bool | None = None

    # Deprecated. Use model_fields
    __fields__ = _V1FieldsDescriptor()  # type: ignore[assignment]

    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,
        # Pydantic 1 accepted numbers for string fields
        coerce_numbers_to_str=True,
        # Pydantic 1 accepted instances of other models for model fields
        from_attributes=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_v1_input(cls, data: Any) -> Any:
        return coerce_v1_input(cls, data)

    @classmethod
    def model_json_schema(
        cls,
        by_alias: bool = True,
        ref_template: str = REF_TEMPLATE,
        schema_generator: type[GenerateJsonSchema] = SettingsJsonSchemaGenerator,
        mode: JsonSchemaMode = "validation",
        *,
        union_format: Literal["any_of", "primitive_type_array"] = "any_of",
    ) -> dict[str, Any]:
        """Return the JSON schema of the settings model.

        The schema has the same structure the settings editor expects
        (Pydantic 1 style), see `ayon_server.settings.json_schema`.
        """
        # Schema generation is expensive and settings models do not change
        # at runtime, so the result is cached (Pydantic 1 did the same).
        # A copy is returned, as the schema is modified by postprocessing.
        key = (by_alias, ref_template, schema_generator, mode, union_format)
        cache = cls.__dict__.get("__ayon_schema_cache__")
        if cache is None:
            cache = {}
            setattr(cls, "__ayon_schema_cache__", cache)
        if key not in cache:
            cache[key] = super().model_json_schema(
                by_alias=by_alias,
                ref_template=ref_template,
                schema_generator=schema_generator,
                mode=mode,
                union_format=union_format,
            )
        return copy.deepcopy(cache[key])

    @classmethod
    def schema(
        cls,
        by_alias: bool = True,
        ref_template: str = REF_TEMPLATE,
    ) -> dict[str, Any]:
        """Backwards compatible alias for model_json_schema."""
        return cls.model_json_schema(by_alias=by_alias, ref_template=ref_template)


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
        if key in new_model_class.model_fields:
            # Construct the key path for nested fields
            key_path = f"{parent_key}.{key}" if parent_key else key
            field = new_model_class.model_fields[key]

            outer_type = strip_optional(field.annotation)
            inner_type = get_inner_type(field.annotation)

            if inspect.isclass(inner_type) and issubclass(
                inner_type, BaseSettingsModel
            ):
                if get_origin(outer_type) is list and isinstance(value, list):
                    new_data[key] = [
                        migrate_settings_overrides(
                            v,
                            get_args(outer_type)[0],
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
                    validated_value = TypeAdapter(outer_type).validate_python(value)
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

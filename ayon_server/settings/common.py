import copy
import functools
import inspect
import re
from collections.abc import Callable
from typing import Annotated, Any, Literal, get_args, get_origin

from pydantic import (
    BaseModel,
    PydanticUserError,
    TypeAdapter,
    ValidationError,
)
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode

from ayon_server.logging import logger
from ayon_server.models.base_model import AyonBaseModel
from ayon_server.models.field_info import V1ModelField, get_inner_type, strip_optional
from ayon_server.models.metaclass import coerce_v1_input
from ayon_server.settings.json_schema import REF_TEMPLATE, SettingsJsonSchemaGenerator

pattern = re.compile(r"(?<!^)(?=[A-Z])")


class _V1FieldsDescriptor:
    """Pydantic 1 style `__fields__` (used by addons)"""

    def __get__(self, obj: Any, owner: type[BaseModel]) -> dict[str, V1ModelField]:
        return {
            name: V1ModelField(name, field_info)
            for name, field_info in owner.model_fields.items()
        }


class BaseSettingsModel(AyonBaseModel):
    _isGroup: bool = False
    _title: str | None = None
    _layout: str | None = None
    _required: bool = False
    _has_studio_overrides: bool | None = None
    _has_project_overrides: bool | None = None
    _has_site_overrides: bool | None = None

    # Deprecated. Use model_fields
    __fields__ = _V1FieldsDescriptor()  # type: ignore[assignment]

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


@functools.cache
def _field_adapter(model: type[BaseModel], key: str) -> TypeAdapter[Any]:
    """Return a validator of a single model field.

    The validator uses the field type, its constraints (ge, pattern...)
    and the model config (lax coercions), so it accepts the same values
    as the model does for the field (except field and model validators).
    """
    field = model.model_fields[key]
    annotation: Any = field.annotation
    if field.metadata:
        annotation = Annotated[(annotation, *field.metadata)]
    try:
        return TypeAdapter(annotation, config=model.model_config)
    except PydanticUserError:
        # Config cannot be set for model types
        return TypeAdapter(annotation)


def _validate_field_value(model: type[BaseModel], key: str, value: Any) -> Any:
    value = coerce_v1_input(model, {key: value})[key]
    return _field_adapter(model, key).validate_python(value)


def _log_dropped(log_context: str, key_path: str, value: Any, reason: str) -> None:
    context = f" {log_context}" if log_context else ""
    logger.warning(
        f"Settings migration{context}: dropping '{key_path}' "
        f"= {str(value)[:70]}: {reason}"
    )


def _merge_overrides(defaults: dict[str, Any], overrides: dict[str, Any]) -> Any:
    result = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_overrides(result[key], value)
        else:
            result[key] = value
    return result


def _drop_invalid_overrides(
    model: type[BaseSettingsModel],
    overrides: dict[str, Any],
    defaults: dict[str, Any],
    log_context: str,
) -> None:
    """Remove overrides, which make the settings invalid.

    Values are validated one by one during the migration, but field
    and model validators may still reject the result. Such overrides
    would break loading the settings.
    """
    for _ in range(100):
        try:
            model.model_validate(_merge_overrides(defaults, overrides))
            return
        except ValidationError as e:
            errors = e.errors()

        dropped = False
        for error in errors:
            if error["type"] == "missing":
                continue
            # Find the deepest override causing the error
            node: Any = overrides
            path: list[str] = []
            for part in error["loc"]:
                if not (isinstance(node, dict) and part in node):
                    break
                path.append(str(part))
                if not isinstance(node[part], dict):
                    break
                node = node[part]
            if not path:
                continue
            parent = overrides
            for part in path[:-1]:
                parent = parent[part]
            if path[-1] not in parent:
                # Already dropped by a previous error
                continue
            value = parent.pop(path[-1])
            _log_dropped(log_context, ".".join(path), value, error["msg"])
            dropped = True

        if not dropped:
            logger.error(
                f"Settings migration {log_context}: migrated settings are invalid "
                f"and the cause cannot be removed: {errors}"
            )
            return


def migrate_settings_overrides(
    old_data: dict[str, Any],
    new_model_class: type[BaseSettingsModel],
    defaults: dict[str, Any],
    custom_conversions: dict[str, Callable[[Any], Any]] = {},
    parent_key: str = "",
    *,
    log_context: str = "",
) -> dict[str, Any]:
    """Migrate settings overrides from old data to new model class.

    Values, which are not compatible with the new model, are dropped
    (and logged). `log_context` (such as the addon name and versions)
    is included in these log messages.
    """

    new_data: dict[str, Any] = {}

    if get_origin(new_model_class) is Annotated:
        args = get_args(new_model_class)
        new_model_class = args[0] if args else new_model_class

    for key, value in old_data.items():
        # Construct the key path for nested fields
        key_path = f"{parent_key}.{key}" if parent_key else key

        if key not in new_model_class.model_fields:
            _log_dropped(log_context, key_path, value, "field no longer exists")
            continue

        field = new_model_class.model_fields[key]

        outer_type = strip_optional(field.annotation)
        inner_type = get_inner_type(field.annotation)

        if inspect.isclass(inner_type) and issubclass(inner_type, BaseSettingsModel):
            if get_origin(outer_type) is list and isinstance(value, list):
                new_data[key] = [
                    migrate_settings_overrides(
                        v,
                        get_args(outer_type)[0],
                        {},
                        custom_conversions,
                        key_path,
                        log_context=log_context,
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
                    log_context=log_context,
                )
            else:
                _log_dropped(log_context, key_path, value, "submodel expected")
        else:
            try:
                new_data[key] = _validate_field_value(new_model_class, key, value)
            except ValidationError as e:
                _log_dropped(log_context, key_path, value, e.errors()[0]["msg"])

    if not parent_key and defaults:
        _drop_invalid_overrides(new_model_class, new_data, defaults, log_context)

    return new_data

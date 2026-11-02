"""Common base of AYON models (RestModel and BaseSettingsModel)."""

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    ModelWrapValidatorHandler,
    ValidationError,
    model_validator,
)

from ayon_server.models.field_info import V1ModelField, v1_model_fields
from ayon_server.models.metaclass import AyonModelMetaclass, coerce_v1_input


class _V1FieldsDescriptor:
    def __get__(self, obj: Any, owner: type[BaseModel]) -> dict[str, V1ModelField]:
        return v1_model_fields(owner)


class AyonBaseModel(BaseModel, metaclass=AyonModelMetaclass):
    """Base of RestModel and BaseSettingsModel. Do not use it directly.

    Keeps the Pydantic 1 behavior of the models, which are also
    defined by addons written for Pydantic 1
    (see AyonModelMetaclass and coerce_v1_input).
    """

    # Pydantic 1 style fields of model instances (deprecated, used by addons).
    # Class access (`Model.__fields__`) is handled by the metaclass.
    __fields__ = _V1FieldsDescriptor()  # type: ignore[assignment]

    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,
        # Pydantic 1 accepted numbers for string fields
        coerce_numbers_to_str=True,
        # Pydantic 1 accepted instances of other models for model fields
        from_attributes=True,
    )

    @model_validator(mode="wrap")
    @classmethod
    def _coerce_v1_input(
        cls,
        data: Any,
        handler: ModelWrapValidatorHandler[Any],
    ) -> Any:
        # Pydantic 1 style coercions are applied only when the validation
        # fails, so validating valid data doesn't pay for them.
        try:
            return handler(data)
        except ValidationError:
            coerced = coerce_v1_input(cls, data)
            if coerced is data:
                raise
            return handler(coerced)

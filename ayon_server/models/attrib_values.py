"""Entity attribute values.

Attribute values of entities are plain dicts (`AttribDict`), validated
against the current attribute definitions. Attributes may change at runtime
(see `AttributeLibrary.reload`), so the validator looks up the current
attribute model on each validation. Entity models, their subclasses and
FastAPI routes using them never need to be rebuilt.

`AttribDict` supports attribute access (`entity.attrib.fps`) and
`model_dump()` for backwards compatibility with the code written for
attribute models (pydantic models), which were used before.
"""

from collections.abc import Callable, Iterable
from typing import Annotated, Any

from pydantic import BaseModel, GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.fields import FieldInfo
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema


class AttribDict(dict[str, Any]):
    """Attribute values of an entity.

    A dict, which additionally supports attribute access. Reading an attribute
    which is not set returns None (as attribute models did for attributes
    without a value).

    Similar to pydantic models, it keeps track of explicitly set attributes
    (`model_fields_set`), so serializing with `exclude_unset` works as before.
    """

    __slots__ = ("_fields_set",)

    def __init__(
        self,
        data: dict[str, Any] | Iterable[tuple[str, Any]] | None = None,
        fields_set: Iterable[str] | None = None,
    ) -> None:
        super().__init__(data or {})
        object.__setattr__(
            self,
            "_fields_set",
            set(self.keys()) if fields_set is None else set(fields_set),
        )

    # Dict behaviour

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self._fields_set.add(key)

    def update(self, *args: Any, **kwargs: Any) -> None:
        data = dict(*args, **kwargs)
        super().update(data)
        self._fields_set.update(data)

    def copy(self) -> "AttribDict":
        return AttribDict(self, self._fields_set)

    def __copy__(self) -> "AttribDict":
        return self.copy()

    def __deepcopy__(self, memo: dict[int, Any]) -> "AttribDict":
        import copy

        return AttribDict(copy.deepcopy(dict(self), memo), self._fields_set)

    def __reduce__(self) -> Any:
        return (AttribDict, (dict(self), self._fields_set))

    # Attribute access (backwards compatibility)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        return self.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        self.pop(name, None)

    # Pydantic model compatibility

    @property
    def model_fields_set(self) -> set[str]:
        return self._fields_set & set(self.keys())

    def model_dump(
        self,
        *,
        exclude_unset: bool = False,
        exclude_none: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return filter_attrib(
            self, exclude_unset=exclude_unset, exclude_none=exclude_none
        )

    def dict(self, **kwargs: Any) -> dict[str, Any]:
        """Deprecated. Use model_dump"""
        return self.model_dump(**kwargs)


def filter_attrib(
    data: dict[str, Any],
    *,
    exclude_unset: bool = False,
    exclude_none: bool = False,
) -> dict[str, Any]:
    fields_set = data.model_fields_set if isinstance(data, AttribDict) else None
    return {
        key: value
        for key, value in data.items()
        if not (exclude_unset and fields_set is not None and key not in fields_set)
        and not (exclude_none and value is None)
    }


class AttribValues:
    """Annotation marker for a field holding attribute values.

    Values are validated using the model returned by `resolver`
    (the current attribute model of the entity type) and stored
    as `AttribDict`.

    When `partial` is False, the result contains all attributes
    (None or default values for the attributes not provided),
    the same way as an attribute model instance did. When `partial`
    is True (used by patch models), only the provided attributes are kept.
    """

    def __init__(
        self,
        resolver: Callable[[], type[BaseModel]],
        partial: bool = False,
    ) -> None:
        self.resolver = resolver
        self.partial = partial

    def resolve(self) -> type[BaseModel]:
        """Return the current attribute model."""
        return self.resolver()

    @property
    def annotation(self) -> Any:
        """Type annotation to be used for the field."""
        return Annotated[AttribDict, self]

    def __call__(self) -> AttribDict:
        """Return default values (usable as default_factory)"""
        return self.validate({})

    # Field definitions are deep-copied when the entity models are generated.
    # The resolver refers to its owner, which must not be copied.

    def __copy__(self) -> "AttribValues":
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> "AttribValues":
        return self

    def validate(self, value: Any, context: Any = None) -> AttribDict:
        model = self.resolve()
        fields_set: set[str] | None = None
        if isinstance(value, AttribDict):
            fields_set = value.model_fields_set
            value = dict(value)
        elif isinstance(value, BaseModel):
            # A copy: it is modified below (the model must not change)
            fields_set = set(value.model_fields_set)
            value = value.model_dump()

        # Raises ValidationError, which pydantic reports with the field location
        instance = model.__pydantic_validator__.validate_python(value, context=context)
        if fields_set is None:
            fields_set = instance.__pydantic_fields_set__
        else:
            fields_set &= instance.__dict__.keys()

        # Attribute models are flat, so the validated values can be used
        # directly (faster than model_dump)
        values = instance.__dict__
        if self.partial:
            partial = {k: v for k, v in values.items() if k in fields_set}
            return AttribDict(partial, fields_set)
        return AttribDict(values, fields_set)

    #
    # Pydantic hooks
    #

    def __get_pydantic_core_schema__(
        self,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        def validate(value: Any, info: core_schema.ValidationInfo) -> AttribDict:
            return self.validate(value, info.context)

        def serialize(value: Any, info: core_schema.SerializationInfo) -> Any:
            if not isinstance(value, dict):
                return value
            if not (
                info.exclude_unset
                or info.exclude_none
                or info.include is not None
                or info.exclude is not None
            ):
                return value
            result = filter_attrib(
                value,
                exclude_unset=info.exclude_unset,
                exclude_none=info.exclude_none,
            )
            if isinstance(info.include, set | dict):
                result = {k: v for k, v in result.items() if k in info.include}
            if isinstance(info.exclude, set | dict):
                result = {k: v for k, v in result.items() if k not in info.exclude}
            return result

        return core_schema.with_info_plain_validator_function(
            validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                serialize,
                info_arg=True,
            ),
        )

    def __get_pydantic_json_schema__(
        self,
        schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        # The schema documents the current attributes. Wrapping the model
        # core schema in a definitions schema makes the generator store
        # the model in the schema definitions and return a reference to it
        # - the same result as for a regular model field.
        model_schema = self.resolve().__pydantic_core_schema__
        if "ref" not in model_schema:
            return handler(model_schema)
        return handler(
            core_schema.definitions_schema(
                core_schema.definition_reference_schema(model_schema["ref"]),
                [model_schema],
            )
        )


def get_attrib_values(annotation_or_field: Any) -> AttribValues | None:
    """Return the AttribValues marker of an annotation or a field, if any.

    Accepts an `Annotated` annotation or a pydantic `FieldInfo`
    (pydantic moves the `Annotated` metadata to `FieldInfo.metadata`)
    """
    metadata: Iterable[Any]
    if isinstance(annotation_or_field, FieldInfo):
        metadata = annotation_or_field.metadata
    else:
        metadata = getattr(annotation_or_field, "__metadata__", ())
    for meta in metadata:
        if isinstance(meta, AttribValues):
            return meta
    return None

"""Entity attribute values.

Attribute values of entities are plain dicts (`AttribDict`) holding
the attributes set on the entity. Attributes are configured at runtime
(see `AttributeLibrary.reload`), so the entity models (and their schemas)
do not depend on them. Values are validated against the current attribute
definitions when they are written (see `entities.models.attrib`).

`AttribDict` supports attribute access (`entity.attrib.fps`) and
`model_dump()` for backwards compatibility with the code written for
attribute models (pydantic models), which were used before.
"""

from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

# Validation context of entities loaded from the database. Their attribute
# values were validated when they were written, so they are trusted
# (invalid values after attribute changes are fixed by fix_attribute_values).
STORED_VALUES = "stored_attrib_values"
STORED_VALUES_CONTEXT = {STORED_VALUES: True}


class AttribDict(dict[str, Any]):
    """Attribute values of an entity.

    A dict, which additionally supports attribute access. Reading an attribute
    which is not set returns None (as attribute models did for attributes
    without a value).
    """

    __slots__ = ()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        return self.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        self.pop(name, None)

    def copy(self) -> "AttribDict":
        return AttribDict(self)

    # Pydantic model compatibility

    def model_dump(
        self, *, exclude_none: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        """Return the values as a plain dict.

        Only the set attributes are stored, so `exclude_unset` has no effect.
        """
        return {k: v for k, v in self.items() if not (exclude_none and v is None)}

    def dict(self, **kwargs: Any) -> dict[str, Any]:
        """Deprecated. Use model_dump"""
        return self.model_dump(**kwargs)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        # A plain object in the schemas: attributes are configured at runtime
        # and their definitions are provided by the attributes endpoint
        dict_schema = core_schema.dict_schema(
            core_schema.str_schema(), core_schema.any_schema()
        )

        def serialize(
            value: Any,
            serializer: core_schema.SerializerFunctionWrapHandler,
            info: core_schema.SerializationInfo,
        ) -> Any:
            # exclude_none applies to the attributes as well (not only to
            # model fields), so unset attributes (None) are not stored
            result = serializer(value)
            if info.exclude_none and isinstance(result, dict):
                return {k: v for k, v in result.items() if v is not None}
            return result

        return core_schema.no_info_after_validator_function(
            cls,
            dict_schema,
            serialization=core_schema.wrap_serializer_function_ser_schema(
                serialize, info_arg=True, schema=dict_schema
            ),
        )

"""Model fields whose model class may be replaced at runtime.

Pydantic 2 compiles the validator and serializer of a model when the
model class is created. A nested model is compiled into its parent, and
FastAPI compiles the models used by a route when the route is registered.
Replacing a nested model class later has no effect on its parents, the
routes using them, or the models inheriting from them.

Custom attributes can be changed while the server is running, so
the attribute models (`FolderAttribModel`...) are regenerated. Fields
which hold them use `DynamicModel`: the parent model compiles a thin
function validator which looks up the current model class on each
validation, and resolves the JSON schema when it is generated, so
parent models never need to be rebuilt.

Usage:

    attrib_type = DynamicModel(lambda: get_current_attrib_model())

    class FolderModel(BaseModel):
        attrib: attrib_type.annotation = Field(default_factory=attrib_type)
"""

from collections.abc import Callable, Sequence
from typing import Annotated, Any

from pydantic import BaseModel, GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.fields import FieldInfo
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema


class DynamicModel:
    """Annotation marker for a field holding a model resolved at runtime."""

    def __init__(self, resolver: Callable[[], type[BaseModel]]) -> None:
        self.resolver = resolver

    def resolve(self) -> type[BaseModel]:
        """Return the current model class."""
        return self.resolver()

    @property
    def annotation(self) -> Any:
        """Type annotation to be used for the field.

        The annotated type is `Any`, because FastAPI collects models
        from field annotations (without the metadata) to generate
        OpenAPI definitions. The actual model is resolved from the metadata.
        """
        return Annotated[Any, self]

    def __call__(self, **kwargs: Any) -> BaseModel:
        """Create an instance of the current model (usable as default_factory)"""
        return self.resolve()(**kwargs)

    # Field definitions are deep-copied when the entity models are generated.
    # The resolver refers to its owner, which must not be copied.

    def __copy__(self) -> "DynamicModel":
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> "DynamicModel":
        return self

    #
    # Pydantic hooks
    #

    def __get_pydantic_core_schema__(
        self,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        def validate(value: Any, info: core_schema.ValidationInfo) -> BaseModel:
            model = self.resolve()
            if isinstance(value, model):
                return value
            if isinstance(value, BaseModel):
                # Instance of another model class. Typically an instance
                # of the model created before the model was replaced.
                value = value.model_dump(exclude_unset=True)
            return model.__pydantic_validator__.validate_python(
                value, context=info.context
            )

        # Serialization is not specified: the value is serialized
        # by its own model serializer (with all the dump options)
        return core_schema.with_info_plain_validator_function(validate)

    def __get_pydantic_json_schema__(
        self,
        schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        # Wrapping the model core schema in a definitions schema makes the
        # generator store the model in the schema definitions and return
        # a reference to it - the same result as for a regular model field.
        model_schema = self.resolve().__pydantic_core_schema__
        if "ref" not in model_schema:
            return handler(model_schema)
        return handler(
            core_schema.definitions_schema(
                core_schema.definition_reference_schema(model_schema["ref"]),
                [model_schema],
            )
        )


def get_dynamic_model(annotation_or_field: Any) -> DynamicModel | None:
    """Return the DynamicModel marker of an annotation or a field, if any.

    Accepts an `Annotated` annotation or a pydantic `FieldInfo`
    (pydantic moves the `Annotated` metadata to `FieldInfo.metadata`)
    """
    metadata: Sequence[Any]
    if isinstance(annotation_or_field, FieldInfo):
        metadata = annotation_or_field.metadata
    else:
        metadata = getattr(annotation_or_field, "__metadata__", ())
    for meta in metadata:
        if isinstance(meta, DynamicModel):
            return meta
    return None

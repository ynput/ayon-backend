"""JSON schema generator for settings models.

The settings editor in the frontend (and addons) were built around
the JSON schema format produced by Pydantic 1. This generator produces
the same structure using Pydantic 2:

- sub-schemas are stored in `definitions` (not `$defs`)
- fields referencing a sub-model are wrapped in `allOf` and always have a title
- optional fields are not expressed as `anyOf [..., null]`
- `None` defaults are not included in the schema
- single-value literals use `enum` instead of `const`
- fixed-length tuples use `items` list instead of `prefixItems`
- fields always have a title, even if it is the same as the model title
- model docstrings are inherited from parent classes
- named tuples (colors) are inlined, not stored in definitions
- empty field descriptions are omitted
"""

import inspect
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue
from pydantic_core import core_schema

from ayon_server.models.base_model import AyonBaseModel

REF_TEMPLATE = "#/definitions/{model}"


def _transform(schema: Any, inline_defs: dict[str, Any]) -> Any:
    """Recursively convert the schema to the Pydantic 1 structure"""
    if isinstance(schema, list):
        return [_transform(item, inline_defs) for item in schema]
    if not isinstance(schema, dict):
        return schema

    ref = schema.get("$ref")
    if isinstance(ref, str) and ref in inline_defs:
        # Inline the referenced definition
        schema = {
            **inline_defs[ref],
            **{k: v for k, v in schema.items() if k != "$ref"},
        }

    if "prefixItems" in schema:
        schema["items"] = schema.pop("prefixItems")

    result = {key: _transform(value, inline_defs) for key, value in schema.items()}

    properties = result.get("properties")
    if isinstance(properties, dict):
        for prop_name, prop in properties.items():
            if not isinstance(prop, dict):
                continue
            if prop.get("description") == "":
                del prop["description"]
            if "$ref" in prop and len(prop) > 1:
                # Wrap `$ref` with sibling keywords into `allOf`
                prop_ref = prop.pop("$ref")
                properties[prop_name] = {"allOf": [{"$ref": prop_ref}], **prop}
    return result


class SettingsJsonSchemaGenerator(GenerateJsonSchema):
    def __init__(
        self,
        by_alias: bool = True,
        ref_template: str = REF_TEMPLATE,
        **kwargs: Any,
    ):
        super().__init__(by_alias=by_alias, ref_template=ref_template, **kwargs)

    def generate(
        self, schema: core_schema.CoreSchema, mode: Any = "validation"
    ) -> JsonSchemaValue:
        json_schema = super().generate(schema, mode=mode)
        definitions = json_schema.pop("$defs", {})

        # Pydantic 1 did not create definitions for tuple-like types
        # (such as named tuples used for colors), they were inlined.
        inline_defs = {}
        for name, definition in list(definitions.items()):
            if definition.get("type") == "array":
                inline_defs[self.ref_template.format(model=name)] = definition
                del definitions[name]

        json_schema = _transform(json_schema, inline_defs)
        if definitions:
            json_schema["definitions"] = _transform(definitions, inline_defs)
        return json_schema

    def handle_ref_overrides(self, json_schema: JsonSchemaValue) -> JsonSchemaValue:
        # Keep sibling keys of `$ref` even if they are the same
        # as in the referenced schema. Titles of fields are used as labels
        return json_schema

    def field_title_should_be_set(self, schema: Any) -> bool:
        return True

    def nullable_schema(self, schema: core_schema.NullableSchema) -> JsonSchemaValue:
        return self.generate_inner(schema["schema"])

    def default_schema(self, schema: core_schema.WithDefaultSchema) -> JsonSchemaValue:
        if schema.get("default") is None:
            # Pydantic 1 does not include None defaults
            return self.generate_inner(schema["schema"])
        return super().default_schema(schema)

    def literal_schema(self, schema: core_schema.LiteralSchema) -> JsonSchemaValue:
        json_schema = super().literal_schema(schema)
        if "const" in json_schema and "enum" not in json_schema:
            json_schema["enum"] = [json_schema.pop("const")]
        return json_schema

    def enum_schema(self, schema: core_schema.EnumSchema) -> JsonSchemaValue:
        json_schema = super().enum_schema(schema)
        json_schema.setdefault("description", "An enumeration.")
        return json_schema

    def model_schema(self, schema: core_schema.ModelSchema) -> JsonSchemaValue:
        json_schema = super().model_schema(schema)
        if "description" not in json_schema:
            # Pydantic 1 inherited docstrings from parent models
            # (but not from the AYON base models)
            for cls in schema["cls"].__mro__[1:]:
                if cls is BaseModel or cls is AyonBaseModel:
                    break
                if doc := cls.__dict__.get("__doc__"):
                    json_schema["description"] = inspect.cleandoc(doc)
                    break
        return json_schema

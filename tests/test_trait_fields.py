import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ayon_server.addons.models import TraitDefinition
from ayon_server.traits.fields import (
    ProjectTraitFields,
    TraitFieldInfo,
    TraitsFilteringSettings,
    TraitUsage,
    apply_filtering_settings,
    field_title,
    get_definition_fields,
    schema_field_type,
)


@pytest.mark.parametrize(
    "schema, expected",
    [
        ({"type": "integer"}, "integer"),
        ({"type": "number"}, "float"),
        ({"type": "boolean"}, "boolean"),
        ({"type": "string"}, "string"),
        ({"type": ["integer", "null"]}, "integer"),
        ({"anyOf": [{"type": "string"}, {"type": "null"}]}, "string"),
        ({"type": "array", "items": {"type": "string"}}, "list_of_strings"),
        ({"type": "array", "items": {"type": "integer"}}, "list_of_integers"),
        ({"enum": ["a", "b", None]}, "string"),
        ({"type": ["string", "null"], "format": "regex"}, None),
        ({"type": "string", "format": "path"}, None),
        ({"type": "object"}, None),
        ({"type": "array", "items": {"type": "object"}}, None),
        ({"type": ["string", "integer"]}, None),
    ],
)
def test_schema_field_type(schema, expected):
    assert schema_field_type(schema) == expected


def test_field_title():
    assert field_title("display_window_width") == "Display Window Width"
    assert field_title("fps") == "FPS"


def test_definition_fields():
    definition = TraitDefinition(
        id="ayon.time.Sequence.v1",
        versionless_id="ayon.time.Sequence",
        version=1,
        name="Sequence",
        schema={
            "properties": {
                "frame_padding": {"type": "integer"},
                "gaps_policy": {
                    "type": ["string", "null"],
                    "enum": ["forbidden", "missing", None],
                },
                "frame_regex": {"type": "string", "format": "regex"},
                "nested": {"type": "object"},
            }
        },
    )
    fields = get_definition_fields(definition)
    assert set(fields) == {"frame_padding", "gaps_policy"}
    assert fields["gaps_policy"].enum == ["forbidden", "missing"]
    assert fields["frame_padding"].title == "Frame Padding"


def _data() -> ProjectTraitFields:
    return ProjectTraitFields(
        traits=[
            TraitUsage(
                id="ayon.2d.PixelBased",
                name="PixelBased",
                fields=[
                    TraitFieldInfo(
                        name="display_window_width", title="W", type="integer"
                    ),
                    TraitFieldInfo(name="pixel_aspect_ratio", title="P", type="float"),
                ],
            ),
            TraitUsage(id="ayon.lifecycle.Persistent", name="Persistent"),
        ]
    )


def test_no_settings_exposes_nothing():
    result = apply_filtering_settings(_data(), None)
    # traits stay for "Has Trait", fields are left out
    assert [t.id for t in result.traits] == [
        "ayon.2d.PixelBased",
        "ayon.lifecycle.Persistent",
    ]
    assert all(not t.fields for t in result.traits)


def test_exposed_traits():
    settings = TraitsFilteringSettings(exposed_traits=["ayon.2d.PixelBased"])
    result = apply_filtering_settings(_data(), settings)
    assert [f.name for f in result.traits[0].fields] == [
        "display_window_width",
        "pixel_aspect_ratio",
    ]


def test_exposed_fields_and_synonyms():
    settings = TraitsFilteringSettings(
        exposed_fields=["ayon.2d.PixelBased/display_window_width"],
        synonyms=[
            {
                "name": "resolution:width",
                "field": "ayon.2d.PixelBased/display_window_width",
            },
            {"name": "", "field": "ignored"},
        ],
    )
    result = apply_filtering_settings(_data(), settings)
    fields = result.traits[0].fields
    assert [f.name for f in fields] == ["display_window_width"]
    assert fields[0].synonyms == ["resolution:width"]

import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ayon_server.addons.models import TraitDefinition
from ayon_server.addons.traits import (
    load_trait_manifest,
    merge_trait_definitions,
    parse_trait_manifest,
)


def make_manifest(traits: dict) -> dict:
    return {"manifestVersion": 1, "addon": "core", "traits": traits}


def make_entry(name: str, schema_hash: str | None = "sha256:a", **definition):
    entry = {
        "definition": {
            "name": name,
            "description": f"{name} trait",
            "schema": {"type": "object", "properties": {}},
            **definition,
        },
        "introducedIn": "1.0.0",
        "deprecated": False,
    }
    if schema_hash is not None:
        entry["hashes"] = {
            "schema": schema_hash,
            "behavior": "sha256:b",
            "meta": "sha256:m",
        }
    return entry


def make_definition(trait_id: str, schema_hash: str | None, **kwargs):
    data = make_manifest({trait_id: make_entry("Trait", schema_hash, **kwargs)})
    return parse_trait_manifest(data)[0]


class TestParseTraitManifest:
    def test_parses_definition(self):
        data = make_manifest(
            {"ayon.2d.PixelBased.v1": make_entry("PixelBased", ui={"group": "2d"})}
        )
        (definition,) = parse_trait_manifest(data)

        assert definition.id == "ayon.2d.PixelBased.v1"
        assert definition.versionless_id == "ayon.2d.PixelBased"
        assert definition.version == 1
        assert definition.name == "PixelBased"
        assert definition.trait_schema == {"type": "object", "properties": {}}
        assert definition.ui == {"group": "2d"}
        assert definition.introduced_in == "1.0.0"
        assert definition.hashes.schema_hash == "sha256:a"

    def test_serializes_with_aliases(self):
        data = make_manifest({"ayon.2d.Image.v1": make_entry("Image")})
        (definition,) = parse_trait_manifest(data)
        serialized = definition.dict(by_alias=True)

        assert serialized["schema"] == {"type": "object", "properties": {}}
        assert serialized["versionlessId"] == "ayon.2d.Image"
        assert serialized["hashes"]["schema"] == "sha256:a"

    def test_entry_key_is_authoritative(self):
        data = make_manifest(
            {"ayon.meta.Tagged.v2": make_entry("Tagged", id="ayon.meta.Tagged.v1")}
        )
        (definition,) = parse_trait_manifest(data)
        assert definition.id == "ayon.meta.Tagged.v2"
        assert definition.version == 2

    def test_id_without_version(self):
        data = make_manifest({"studio.custom": make_entry("Custom")})
        (definition,) = parse_trait_manifest(data)
        assert definition.versionless_id == "studio.custom"
        assert definition.version is None

    def test_skips_invalid_entries(self):
        data = make_manifest(
            {
                "ayon.2d.Image.v1": make_entry("Image"),
                "ayon.2d.Broken.v1": {"definition": {"schema": "not an object"}},
            }
        )
        definitions = parse_trait_manifest(data)
        assert [d.id for d in definitions] == ["ayon.2d.Image.v1"]

    def test_unsupported_manifest_version(self):
        with pytest.raises(ValueError):
            parse_trait_manifest({"manifestVersion": 99, "traits": {}})


class TestLoadTraitManifest:
    def test_missing_file(self, tmp_path):
        assert load_trait_manifest(str(tmp_path / "traits.json")) == []

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "traits.json"
        path.write_text("{not json", encoding="utf-8")
        assert load_trait_manifest(str(path)) == []

    def test_valid_file(self, tmp_path):
        path = tmp_path / "traits.json"
        data = make_manifest({"ayon.2d.Image.v1": make_entry("Image")})
        path.write_text(json.dumps(data), encoding="utf-8")
        definitions = load_trait_manifest(str(path))
        assert [d.id for d in definitions] == ["ayon.2d.Image.v1"]


class TestMergeTraitDefinitions:
    def test_same_definition_merges_versions(self):
        trait_id = "ayon.2d.Image.v1"
        items, conflicts = merge_trait_definitions(
            [
                ("core", "1.0.0", [make_definition(trait_id, "sha256:a")]),
                ("core", "1.1.0", [make_definition(trait_id, "sha256:a")]),
            ]
        )

        assert conflicts == []
        (item,) = items
        assert item.addon_name == "core"
        assert item.addon_versions == ["1.0.0", "1.1.0"]
        assert item.conflict is False

    def test_newest_definition_wins(self):
        trait_id = "ayon.2d.Image.v1"
        items, _ = merge_trait_definitions(
            [
                ("core", "1.0.0", [make_definition(trait_id, "sha256:a")]),
                (
                    "core",
                    "1.1.0",
                    [make_definition(trait_id, "sha256:a", description="New")],
                ),
            ]
        )
        assert items[0].description == "New"

    def test_schema_change_is_conflict(self):
        trait_id = "ayon.time.FrameRanged.v2"
        items, conflicts = merge_trait_definitions(
            [
                ("core", "1.0.0", [make_definition(trait_id, "sha256:a")]),
                ("core", "1.1.0", [make_definition(trait_id, "sha256:changed")]),
                ("core", "1.2.0", [make_definition(trait_id, "sha256:changed")]),
            ]
        )

        (item,) = items
        assert item.conflict is True
        assert item.addon_versions == ["1.0.0", "1.1.0", "1.2.0"]
        (conflict,) = conflicts
        assert conflict.trait_id == trait_id
        assert conflict.summary()["sources"][0] == {
            "addonName": "core",
            "addonVersion": "1.0.0",
            "schemaHash": "sha256:a",
        }

    def test_same_id_from_other_addon_is_conflict(self):
        trait_id = "ayon.2d.Image.v1"
        items, conflicts = merge_trait_definitions(
            [
                ("core", "1.0.0", [make_definition(trait_id, "sha256:a")]),
                ("other", "0.1.0", [make_definition(trait_id, "sha256:a")]),
            ]
        )

        (item,) = items
        assert item.conflict is True
        assert item.addon_name == "other"
        assert item.addon_versions == ["0.1.0"]
        assert len(conflicts) == 1

    def test_missing_hashes_compare_schema(self):
        trait_id = "ayon.2d.Image.v1"
        same, conflicts = merge_trait_definitions(
            [
                ("core", "1.0.0", [make_definition(trait_id, None)]),
                ("core", "1.1.0", [make_definition(trait_id, None)]),
            ]
        )
        assert conflicts == []

        changed_schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        _, conflicts = merge_trait_definitions(
            [
                ("core", "1.0.0", [make_definition(trait_id, None)]),
                (
                    "core",
                    "1.1.0",
                    [make_definition(trait_id, None, schema=changed_schema)],
                ),
            ]
        )
        assert len(conflicts) == 1

    def test_different_traits_are_kept(self):
        items, conflicts = merge_trait_definitions(
            [
                (
                    "core",
                    "1.0.0",
                    [
                        make_definition("ayon.content.FileLocation.v1", "sha256:a"),
                        make_definition("ayon.content.FileLocation.v2", "sha256:b"),
                    ],
                ),
            ]
        )
        assert conflicts == []
        assert {item.id for item in items} == {
            "ayon.content.FileLocation.v1",
            "ayon.content.FileLocation.v2",
        }

    def test_definition_type(self):
        definition = make_definition("ayon.2d.Image.v1", "sha256:a")
        assert isinstance(definition, TraitDefinition)

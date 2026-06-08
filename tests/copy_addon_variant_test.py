import asyncio
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from api.addons import configuration


def test_copy_addon_variant_uses_target_version_and_skips_projects_by_default():
    calls: list[tuple] = []

    async def fake_fetch(query, addon_name):
        assert addon_name == "example"
        return [{"production_version": "1.0.0", "staging_version": "2.0.0"}]

    def fake_addon(addon_name, addon_version):
        return (addon_name, addon_version)

    async def fake_migrate(
        source_addon,
        target_addon,
        source_variant,
        target_variant,
        with_projects,
    ):
        calls.append(
            (
                source_addon,
                target_addon,
                source_variant,
                target_variant,
                with_projects,
            )
        )
        return []

    original_fetch = configuration.Postgres.fetch
    original_addon = configuration.AddonLibrary.addon
    original_migrate = configuration.migrate_addon_settings
    configuration.Postgres.fetch = fake_fetch
    configuration.AddonLibrary.addon = fake_addon
    configuration.migrate_addon_settings = fake_migrate
    try:
        asyncio.run(
            configuration.copy_addon_variant(
                addon_name="example",
                copy_from="production",
                copy_to="staging",
            )
        )
    finally:
        configuration.Postgres.fetch = original_fetch
        configuration.AddonLibrary.addon = original_addon
        configuration.migrate_addon_settings = original_migrate

    assert calls == [
        (
            ("example", "1.0.0"),
            ("example", "2.0.0"),
            "production",
            "staging",
            False,
        )
    ]


def test_copy_addon_variant_can_include_project_overrides():
    calls: list[bool] = []

    async def fake_fetch(query, addon_name):
        return [{"production_version": "1.2.0", "staging_version": "1.3.0"}]

    def fake_addon(addon_name, addon_version):
        return {"name": addon_name, "version": addon_version}

    async def fake_migrate(
        source_addon,
        target_addon,
        source_variant,
        target_variant,
        with_projects,
    ):
        calls.append(with_projects)
        return []

    original_fetch = configuration.Postgres.fetch
    original_addon = configuration.AddonLibrary.addon
    original_migrate = configuration.migrate_addon_settings
    configuration.Postgres.fetch = fake_fetch
    configuration.AddonLibrary.addon = fake_addon
    configuration.migrate_addon_settings = fake_migrate
    try:
        asyncio.run(
            configuration.copy_addon_variant(
                addon_name="example",
                copy_from="production",
                copy_to="staging",
                with_project_overrides=True,
            )
        )
    finally:
        configuration.Postgres.fetch = original_fetch
        configuration.AddonLibrary.addon = original_addon
        configuration.migrate_addon_settings = original_migrate

    assert calls == [True]

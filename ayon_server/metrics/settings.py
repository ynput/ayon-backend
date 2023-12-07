from ayon_server.addons.library import AddonLibrary
from ayon_server.lib.postgres import Postgres
from ayon_server.settings.overrides import list_overrides
from ayon_server.types import Field, OPModel


class SettingsOverrides(OPModel):
    """Settings overrides model"""

    project_name: str | None = Field(None, title="Project name")
    addon_name: str | None = Field(None, title="Addon name")
    addon_version: str | None = Field(None, title="Addon version")
    paths: list[list[str]] | None = Field(None, title="Path")


async def get_studio_settings_overrides(saturated: bool) -> list[SettingsOverrides]:

    query = "SELECT addon_name, addon_version, data FROM settings WHERE variant = 'production';"

    results = []

    async for row in Postgres.iterate(query):
        addon_name = row["addon_name"]
        addon_version = row["addon_version"]
        data = row["data"]

        try:
            addon = AddonLibrary.addon(addon_name, addon_version)
        except Exception:
            continue

        if (default_settings := await addon.get_default_settings()) is None:
            continue

        paths = []
        overrides = list_overrides(default_settings, data)
        for override in overrides.values():
            if override.get("inGroup"):
                continue
            if override.get("type") == "branch":
                continue
            paths.append(override["path"])

        results.append(
            SettingsOverrides(
                project_name=None,
                addon_name=addon_name,
                addon_version=addon_version,
                paths=paths,
            )
        )

    return results

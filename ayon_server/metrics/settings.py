from ayon_server.addons.library import AddonLibrary
from ayon_server.lib.postgres import Postgres
from ayon_server.settings.overrides import list_overrides
from ayon_server.types import Field, OPModel


class SettingsOverrides(OPModel):
    """Settings overrides model"""

    addon_name: str | None = Field(
        None,
        title="Addon name",
        example="resolve",
    )
    addon_version: str | None = Field(
        None,
        title="Addon version",
        example="1.0.0",
    )
    paths: list[list[str]] | None = Field(
        None,
        title="Path",
        description="List of paths to settings, which have a studio override",
        example=[["imageio", "ocio_config", "override_global_config"]],
    )


async def get_studio_settings_overrides(
    saturated: bool = False,
    system: bool = False,
) -> list[SettingsOverrides]:
    """Studio settings overrides

    We track what settings are overridden in the studio settings.
    This helps us determine, which settins are used the most and which
    settings are not used at all. This is used to determine how we should
    organize the settings in the UI and how the settings could be improved.
    """

    query = """
    SELECT addon_name, addon_version, data
    FROM public.settings WHERE variant = 'production';
    """

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
        try:
            overrides = list_overrides(default_settings, data)
        except Exception:
            # TODO:
            # Catched because of this exception. Fix later:
            # File "/backend/ayon_server/settings/overrides.py",
            # line 115, in list_overrides
            #     ovr = override[name][i]
            #                         ^^^
            # IndexError: list index out of range
            continue

        for override in overrides.values():
            if override.get("inGroup"):
                continue
            if override.get("type") == "branch":
                continue
            paths.append(override["path"])

        if not paths:
            continue
        results.append(
            SettingsOverrides(
                project_name=None,
                addon_name=addon_name,
                addon_version=addon_version,
                paths=paths,
            )
        )

    return results

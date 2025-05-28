from typing import Annotated, Any

from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.settings import BaseSettingsModel, SettingsField


class CustomizationModel(BaseSettingsModel):
    login_background: Annotated[
        str | None,
        SettingsField(
            title="Login Background",
            disabled=True,
        ),
    ] = None

    studio_logo: Annotated[
        str | None,
        SettingsField(
            title="Studio Logo",
            disabled=True,
        ),
    ] = None

    motd: Annotated[
        str,
        SettingsField(
            title="Login Page Message",
            description="The message that is displayed to users on the login "
            "page. Markdown syntax is supported.",
            example="Welcome to Ayon!",
            widget="textarea",
        ),
    ] = ""


class ProjectOptionsModel(BaseSettingsModel):
    project_code_regex: Annotated[
        str,
        SettingsField(
            title="Project Code Regex",
            description=(
                "A regular expression that is used "
                "to create project code from the project name."
            ),
        ),
    ] = "^.{0,3}"


class ChangelogSettingsModel(BaseSettingsModel):
    show_changelog_to_users: Annotated[
        bool,
        SettingsField(
            title="Show Changelog to Users",
            description="If enabled, the changelog will be shown to normal users.",
        ),
    ] = True


class ServerConfigModel(BaseSettingsModel):
    _layout = "root"

    studio_name: Annotated[
        str,
        SettingsField(
            description="The name of the studio",
            example="Ynput",
        ),
    ] = ""

    customization: Annotated[
        CustomizationModel,
        SettingsField(
            title="Customization",
            description="Customization options for the login page",
            default_factory=CustomizationModel,
        ),
    ]

    project_options: Annotated[
        ProjectOptionsModel,
        SettingsField(
            title="Project Options",
            default_factory=ProjectOptionsModel,
        ),
    ]

    changelog: Annotated[
        ChangelogSettingsModel,
        SettingsField(
            title="Changelog Settings",
            description="Settings for the changelog feature",
            default_factory=ChangelogSettingsModel,
        ),
    ]


def migrate_server_config(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Migrate the server configuration from the old format to the new format."""

    return config_dict


async def build_server_config_cache() -> dict[str, Any]:
    q = "SELECT value FROM public.config WHERE key = 'serverConfig'"
    res = await Postgres.fetchrow(q)
    if not res:
        data = {}
    else:
        data = res["value"]
    data = migrate_server_config(data)
    await Redis.set_json("server", "config", data)
    return data


async def get_server_config_overrides() -> dict[str, Any]:
    data = await Redis.get_json("server", "config")
    if data is None:
        return await build_server_config_cache()
    return data


async def get_server_config() -> ServerConfigModel:
    """Return the server configuration."""
    data = await Redis.get_json("server", "config")
    if data is None:
        data = await build_server_config_cache()
    return ServerConfigModel(**data)


async def save_server_config_data(data: dict[str, Any]) -> None:
    await Postgres.execute(
        """
        INSERT INTO public.config (key, value)
        VALUES ('serverConfig', $1)
        ON CONFLICT (key) DO UPDATE SET value = $1
        """,
        data,
    )
    await build_server_config_cache()

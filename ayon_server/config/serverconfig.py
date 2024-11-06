from typing import Any

from ayon_server.config.ayonconfig import ayonconfig
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.settings import BaseSettingsModel, SettingsField


class ServerConfigModel(BaseSettingsModel):
    _layout: str = "root"
    studio_name: str = SettingsField(
        "",
        description="The name of the studio",
        example="Ynput",
    )
    motd: str = SettingsField(
        ayonconfig.motd or "",
        description="The message of the day that "
        "is displayed to users on the login page"
        "Markdown syntax is supported.",
        example="Welcome to Ayon!",
    )


def migrate_server_config(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Migrate the server configuration from the old format to the new format."""

    return config_dict


async def build_server_config_cache() -> dict[str, Any]:
    q = "SELECT value FROM config WHERE key = 'serverConfig'"
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

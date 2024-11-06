from typing import Any

from ayon_server.api.dependencies import CurrentUser, CurrentUserOptional
from ayon_server.api.responses import EmptyResponse
from ayon_server.config.serverconfig import ServerConfigModel, build_server_config_cache
from ayon_server.config.serverconfig import get_server_config as _get_server_config
from ayon_server.config.serverconfig import (
    get_server_config_overrides as _get_server_config_overrides,
)
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.settings.overrides import extract_overrides, list_overrides
from ayon_server.settings.postprocess import postprocess_settings_schema

from .router import router


@router.get("/config/schema")
async def get_server_config_schema(_: CurrentUserOptional) -> dict[str, Any]:
    schema = ServerConfigModel.schema()
    context: dict[str, Any] = {}
    await postprocess_settings_schema(schema, ServerConfigModel, context=context)
    schema["title"] = "Server Configuration"
    return schema


@router.get("/config")
async def get_server_config(user: CurrentUser) -> ServerConfigModel:
    """Get the server configuration."""

    if not user.is_admin:
        raise ForbiddenException(
            "Only administrators can view the server configuration"
        )

    return await _get_server_config()


@router.get("/config/overrides")
async def get_server_config_overrides(user: CurrentUser) -> dict[str, Any]:
    if not user.is_admin:
        raise ForbiddenException(
            "Only administrators can view the server configuration"
        )
    server_config = await _get_server_config()
    server_overrides = await _get_server_config_overrides()
    return list_overrides(server_config, server_overrides)


@router.post("/config")
async def set_server_config(
    user: CurrentUser,
    payload: dict[str, Any],
) -> EmptyResponse:
    """Set the server configuration"""

    if not user.is_admin:
        raise ForbiddenException(
            "Only administrators can change the server configuration"
        )

    explicit_pins = payload.pop("__pinned_fields__", None)
    explicit_unpins = payload.pop("__unpinned_fields__", None)
    payload_obj = ServerConfigModel(**payload)

    original = await _get_server_config()
    existing = await _get_server_config_overrides()
    data = extract_overrides(
        original,
        payload_obj,
        existing=existing,
        explicit_pins=explicit_pins,
        explicit_unpins=explicit_unpins,
    )

    await Postgres.execute(
        """
        INSERT INTO config (key, value)
        VALUES ('serverConfig', $1)
        ON CONFLICT (key) DO UPDATE SET value = $1
        """,
        data,
    )

    await build_server_config_cache()
    return EmptyResponse()

from typing import Any

from ayon_server.api.dependencies import CurrentUser, CurrentUserOptional
from ayon_server.api.responses import EmptyResponse
from ayon_server.config.serverconfig import ServerConfigModel, save_server_config_data
from ayon_server.config.serverconfig import get_server_config as _get_server_config
from ayon_server.config.serverconfig import (
    get_server_config_overrides as _get_server_config_overrides,
)
from ayon_server.exceptions import ForbiddenException
from ayon_server.settings.overrides import extract_overrides, list_overrides
from ayon_server.settings.postprocess import postprocess_settings_schema

from .router import router


@router.get("/config/schema")
async def get_server_config_schema(_: CurrentUserOptional) -> dict[str, Any]:
    schema = ServerConfigModel.schema()
    await postprocess_settings_schema(schema, ServerConfigModel)
    schema["title"] = "Server Configuration"
    return schema


@router.get("/config")
async def get_server_config(user: CurrentUser) -> ServerConfigModel:
    """Get the server configuration."""
    if not user.is_admin:
        msg = "Only administrators can view the server configuration"
        raise ForbiddenException(msg)
    return await _get_server_config()


@router.get("/config/overrides")
async def get_server_config_overrides(user: CurrentUser) -> dict[str, Any]:
    if not user.is_admin:
        msg = "Only administrators can view the server configuration"
        raise ForbiddenException(msg)
    server_overrides = await _get_server_config_overrides()
    server_config = ServerConfigModel(**server_overrides)
    return list_overrides(server_config, server_overrides)


@router.post("/config")
async def set_server_config(
    user: CurrentUser,
    payload: ServerConfigModel,
) -> EmptyResponse:
    """Set the server configuration"""

    if not user.is_admin:
        msg = "Only administrators can change the server configuration"
        raise ForbiddenException(msg)

    original = ServerConfigModel()
    data = extract_overrides(original, payload)

    await save_server_config_data(data)
    return EmptyResponse()

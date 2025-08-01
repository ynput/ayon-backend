from typing import Any

from fastapi import Path

from ayon_server.api.dependencies import CurrentUser, CurrentUserOptional
from ayon_server.api.responses import EmptyResponse
from ayon_server.config.serverconfig import ServerConfigModel, save_server_config_data
from ayon_server.config.serverconfig import get_server_config as _get_server_config
from ayon_server.config.serverconfig import (
    get_server_config_overrides as _get_server_config_overrides,
)
from ayon_server.exceptions import BadRequestException, ForbiddenException
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

    original = ServerConfigModel()  # type: ignore[call-arg]
    data = extract_overrides(original, payload)

    await save_server_config_data(data)
    return EmptyResponse()


all_users_keys = [
    "studio_name",
    "project_options",
]


@router.get("/config/value/{key}")
async def get_config_value(
    user: CurrentUser,
    key: str = Path(..., description="The key of the configuration value to retrieve"),
) -> Any:
    config = await _get_server_config()
    config_dict = config.dict()

    try:
        value = config_dict[key]
    except KeyError:
        raise BadRequestException(f"Config key '{key}' not found")

    if key in all_users_keys:
        return value

    if not user.is_admin:
        raise ForbiddenException(
            "Only administrators can view this configuration value"
        )

    return value

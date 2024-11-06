from typing import Any

from ayon_server.api.dependencies import CurrentUser, CurrentUserOptional
from ayon_server.api.responses import EmptyResponse
from ayon_server.config.serverconfig import ServerConfigModel, build_server_config_cache
from ayon_server.exceptions import ForbiddenException
from ayon_server.settings.postprocess import postprocess_settings_schema

from .router import router


@router.get("/config/schema")
async def get_server_config_schema(_: CurrentUserOptional) -> dict[str, Any]:
    schema = ServerConfigModel.schema()
    context = {}
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

    return ServerConfigModel()


@router.get("/config/overrides")
async def get_server_config_overrides(user: CurrentUser) -> dict[str, Any]:
    if not user.is_admin:
        raise ForbiddenException(
            "Only administrators can view the server configuration"
        )

    return {}


@router.post("/config")
async def set_server_config(
    user: CurrentUser,
    payload: ServerConfigModel,
) -> EmptyResponse:
    """Set the server configuration"""

    if not user.is_admin:
        raise ForbiddenException(
            "Only administrators can change the server configuration"
        )

    #

    await build_server_config_cache()
    return EmptyResponse()

from fastapi import Request

from ayon_server.api.dependencies import CurrentUser, CurrentUserOptional
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import ForbiddenException

from .router import router


@router.get("/config/{key}")
async def get_server_config_value(
    user: CurrentUserOptional,
    key: str,
):
    pass


@router.put("/config/{key}")
async def set_server_config_value(
    user: CurrentUser, key: str, request: Request
) -> EmptyResponse:
    """Return a list of Ayon URIs for the given entity IDs."""

    if not user.is_admin:
        raise ForbiddenException(
            "Only administrators can set server configuration values."
        )

    return EmptyResponse()

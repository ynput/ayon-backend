from fastapi import Response
from nxtools import logging

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.system import clear_server_restart_required, require_server_restart
from ayon_server.events import dispatch_event
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from . import info, metrics, secrets, sites
from .router import router

assert info
assert metrics
assert secrets
assert sites


@router.post("/system/restart", response_class=Response, tags=["System"])
async def request_server_restart(user: CurrentUser):
    if not user.is_manager:
        raise ForbiddenException(
            "Only managers and administrators can restart the server"
        )

    if user.is_guest:
        raise ForbiddenException("Guests cannot restart the server")

    logging.info(f"{user.name} requested server restart", user=user.name)
    await dispatch_event("server.restart_requested", user=user.name)
    return Response(status_code=204)


class RestartRequiredModel(OPModel):
    required: bool = Field(..., description="Whether the server requires a restart")


@router.get("/system/restartRequired", tags=["System"])
async def get_restart_required() -> RestartRequiredModel:
    # we ignore super new restart required events,
    # because they might not be cleared yet.

    await Postgres.fetch(
        """
        SELECT * FROM events
        WHERE topic='server.restart_required'
        AND created_at < now() - interval ' 2 seconds'
        """
    )

    return RestartRequiredModel(required=False)


@router.post("/system/restartRequired", tags=["System"])
async def set_restart_required(
    request: RestartRequiredModel,
    user: CurrentUser,
):
    """Set the server restart required flag."""
    if request.required:
        await require_server_restart(user.name)
    else:
        await clear_server_restart_required()

    if not user.is_admin:
        raise ForbiddenException("Only administrators can set server restart required")

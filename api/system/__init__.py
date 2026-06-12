__all__ = [
    "frontend_modules",
    "info",
    "metrics",
    "secrets",
    "sites",
    "dbimport",
]

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.system import clear_server_restart_required, require_server_restart
from ayon_server.events import EventStream
from ayon_server.exceptions import ForbiddenException
from ayon_server.installer.hotreload import get_hotreload_manager
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from fastapi import Response

from . import dbimport, frontend_modules, info, metrics, secrets, sites
from .router import router


@router.post("/system/restart", response_class=Response)
async def request_server_restart(user: CurrentUser):
    if not user.is_manager:
        raise ForbiddenException(
            "Only managers and administrators can restart the server"
        )

    if user.is_guest:
        raise ForbiddenException("Guests cannot restart the server")

    logger.info(f"{user.name} requested server restart")
    await EventStream.dispatch("server.restart_requested", user=user.name)
    return Response(status_code=204)


class RestartRequiredModel(OPModel):
    required: bool = Field(..., description="Whether the server requires a restart")
    reason: str | None = Field(None, description="The reason for the restart")


@router.get("/system/restartRequired")
async def get_restart_required() -> RestartRequiredModel:
    """Get the server restart required flag.

    This will return whether the server requires a restart, and the reason for it.
    """

    # we ignore super new restart required events,
    # because they might not be cleared yet.

    res = await Postgres.fetch(
        """
        SELECT description FROM events
        WHERE topic='server.restart_required'
        AND created_at < now() - interval ' 2 seconds'
        """
    )
    if not res:
        return RestartRequiredModel(required=False, reason=None)

    return RestartRequiredModel(required=True, reason=res[0]["description"])


@router.post("/system/restartRequired", response_model_exclude_none=True)
async def set_restart_required(
    request: RestartRequiredModel,
    user: CurrentUser,
):
    """Set the server restart required flag.

    This will notify the administrators that the server needs to be restarted.
    When the server is ready to restart, the administrator can use
    restart_server (using /api/system/restart) to trigger server.restart_requested
    event, which (captured by messaging) will trigger restart_server function
    and restart the server.

    Human-readable reason for the restart can be provided in the `reason` field.
    """
    if request.required:
        await require_server_restart(user.name)
    else:
        await clear_server_restart_required()

    if not user.is_admin:
        raise ForbiddenException("Only administrators can set server restart required")


class ReloadStatusModel(OPModel):
    """Model for hot-reload status information."""

    last_reload: str | None = Field(
        None,
        description="ISO timestamp of the last successful hot-reload",
    )
    reload_count: int = Field(
        0,
        description="Total number of successful hot-reloads since server start",
    )
    callbacks_registered: int = Field(
        0,
        description="Number of reload callbacks registered",
    )


@router.get("/health/reload")
async def get_reload_status() -> ReloadStatusModel:
    """Get hot-reload status information.

    This endpoint provides information about the hot-reload subsystem,
    including when the last reload occurred and how many reloads have
    been performed since server start.

    This is useful for:
    - Monitoring reload activity
    - Verifying that hot-reloads are working
    - Debugging addon installation issues
    """
    manager = get_hotreload_manager()
    status = await manager.get_status()

    return ReloadStatusModel(
        last_reload=status["last_reload"],
        reload_count=status["reload_count"],
        callbacks_registered=status["callbacks_registered"],
    )

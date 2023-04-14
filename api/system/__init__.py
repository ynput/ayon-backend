from fastapi import Depends, Response
from nxtools import logging

from ayon_server.api import dep_current_user
from ayon_server.entities import UserEntity
from ayon_server.events import dispatch_event
from ayon_server.exceptions import ForbiddenException

from . import info, metrics, secrets
from .router import router

assert info
assert metrics
assert secrets


@router.post("/system/restart", response_class=Response, tags=["System"])
async def request_server_restart(user: UserEntity = Depends(dep_current_user)):
    if not user.is_manager:
        raise ForbiddenException(
            "Only managers and administrators can restart the server"
        )

    if user.is_guest:
        raise ForbiddenException("Guests cannot restart the server")

    logging.info(f"{user.name} requested server restart", user=user.name)
    await dispatch_event("server.restart_requested", user=user.name)
    return Response(status_code=204)

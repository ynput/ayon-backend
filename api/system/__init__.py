from fastapi import APIRouter, Depends, Response
from nxtools import logging

from openpype.api import dep_current_user
from openpype.entities import UserEntity
from openpype.events import dispatch_event
from openpype.exceptions import ForbiddenException

router = APIRouter(
    prefix="/system",
    tags=["System"],
)


@router.post("/restart", response_class=Response)
async def request_server_restart(user: UserEntity = Depends(dep_current_user)):
    if not user.is_manager:
        raise ForbiddenException(
            "Only managers and administrators can restart the server"
        )
    logging.info(f"{user.name} requested server restart", user=user.name)
    await dispatch_event("server.restart_requested", user=user.name)
    return Response(status_code=204)

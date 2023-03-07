from fastapi import Depends

from ayon_server.api.dependencies import dep_current_user
from ayon_server.auth.session import Session, SessionModel
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException

from .router import router


@router.get("/sessions")
async def list_active_sessions(
    user: UserEntity = Depends(dep_current_user),
) -> list[SessionModel]:
    if not user.is_manager:
        raise ForbiddenException()

    result: list[SessionModel] = []
    async for row in Session.list():
        result.append(row)

    return result

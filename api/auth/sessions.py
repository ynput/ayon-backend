from fastapi import Depends

from ayon_server.api.dependencies import dep_current_user
from ayon_server.auth.session import Session
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException

from .router import router


@router.get("/sessions")
async def list_active_sessions(
    #  user: UserEntity = Depends(dep_current_user),
) -> UserEntity.model.main_model:  # type: ignore

    result = []

    async for row in Session.list():
        result.append(row)

    return result
    # if not user.is_manager:
    #     raise ForbiddenException()

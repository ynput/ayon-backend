from fastapi import Depends

from ayon_server.api.dependencies import dep_current_user
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException

from .router import router


@router.get("")
async def list_active_sessions(
    user: UserEntity = Depends(dep_current_user),
) -> UserEntity.model.main_model:  # type: ignore

    if not user.is_manager:
        raise ForbiddenException()

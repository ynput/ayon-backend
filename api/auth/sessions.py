from fastapi import Depends

from openpype.api.dependencies import dep_current_user
from openpype.entities import UserEntity
from openpype.exceptions import ForbiddenException

from .router import router


@router.get("")
async def list_active_sessions(
    user: UserEntity = Depends(dep_current_user),
) -> UserEntity.model.main_model:  # type: ignore

    if not user.is_manager:
        raise ForbiddenException()

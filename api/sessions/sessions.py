from fastapi import APIRouter, Depends

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user
from openpype.entities import UserEntity
from openpype.exceptions import ForbiddenException

router = APIRouter(
    prefix="/sessions",
    tags=["Sessions"],
    responses={401: ResponseFactory.error(401)},
)


@router.get("")
async def list_active_sessions(
    user: UserEntity = Depends(dep_current_user),
) -> UserEntity.model.main_model:  # type: ignore

    if not user.is_manager:
        raise ForbiddenException()

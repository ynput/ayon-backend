from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.auth_utils import AuthUtils, UserPoolModel

from .router import router


@router.get("/pools")
async def get_user_pools(user: CurrentUser) -> list[UserPoolModel]:
    """Get list of user pools"""
    if not user.is_manager:
        raise ForbiddenException("Only managers can access this endpoint")
    return await AuthUtils.get_user_pools()

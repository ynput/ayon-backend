from ayon_server.access.utils import AccessChecker
from ayon_server.entities.user import UserEntity
from ayon_server.exceptions import ForbiddenException

from .common import ThumbnailInfo


async def ensure_accessible(thumbnail_info: ThumbnailInfo, user: UserEntity) -> None:
    if user.is_manager:
        return

    # we don't need to check access to the project, because it was already
    # checked by ProjectName dependency at this point

    access_checker = AccessChecker()
    await access_checker.load(user, thumbnail_info["project_name"])

    if access_checker[thumbnail_info["path"]]:
        return

    raise ForbiddenException("You don't have access to this thumbnail")

from ayon_server.access.utils import parse_permset
from ayon_server.entities.user import UserEntity

from .common import ThumbnailInfo


async def get_readable_folders(user: UserEntity, project_name: str) -> set[str] | None:
    if user.is_manager:
        return None

    perms = user.permissions(project_name)
    permset = perms.__getattribute__("read")
    folder_list = await parse_permset(user, project_name, "read", permset)

    print("Readable folders:", folder_list)


async def ensure_accessible(thumbnail_info: ThumbnailInfo, user: UserEntity) -> None:
    if user.is_manager:
        return

    # we don't need to check access to the project, because it was already
    # checked by ProjectName dependency at this point
    #
    print("Ensuring access to thumbnail:", thumbnail_info)
    readable_folders = await get_readable_folders(user, thumbnail_info["project_name"])
    print("Readable folders for user:", readable_folders)

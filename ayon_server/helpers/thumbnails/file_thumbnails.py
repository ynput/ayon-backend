from typing import Protocol

from ayon_server.entities.folder import FolderEntity
from ayon_server.entities.task import TaskEntity
from ayon_server.entities.user import UserEntity
from ayon_server.entities.version import VersionEntity
from ayon_server.entities.workfile import WorkfileEntity
from ayon_server.helpers.preview import obtain_file_preview
from ayon_server.utils.hashing import create_uuid


class EntityWithThumbnail(Protocol):
    id: str
    thumbnail_id: str | None


async def create_file_thumbnail(
    project_name: str,
    file_id: str,
    *,
    user: str | UserEntity | None = None,
    thumbnail_id: str | None = None,
    entity: FolderEntity | TaskEntity | VersionEntity | WorkfileEntity | None = None,
) -> str | None:
    """Creates a thumbnail for a given file and returns its ID.

    If an entity is provided and it doesn't already have a thumbnail, the
    generated thumbnail will also be associated with that entity.
    """

    if thumbnail_id is None:
        thumbnail_id = create_uuid()

    r = await obtain_file_preview(
        project_name,
        file_id,
        thumbnail=True,
        for_entity=entity,
        thumbnail_id=thumbnail_id,
        user=user,
    )

    return thumbnail_id if r else None

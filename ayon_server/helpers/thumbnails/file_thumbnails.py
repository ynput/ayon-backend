from typing import Protocol

from ayon_server.entities.folder import FolderEntity
from ayon_server.entities.task import TaskEntity
from ayon_server.entities.user import UserEntity
from ayon_server.entities.version import VersionEntity
from ayon_server.entities.workfile import WorkfileEntity
from ayon_server.helpers.preview import obtain_file_preview
from ayon_server.helpers.thumbnails import store_thumbnail
from ayon_server.lib.postgres import Postgres
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
) -> str:
    """Creates a thumbnail for a given file and returns its ID.

    If an entity is provided, the thumbnail will also be associated with that entity.
    """

    if thumbnail_id is None:
        thumbnail_id = create_uuid()

    pvw_bytes = await obtain_file_preview(project_name, file_id, thumbnail=True)
    user_name = user.name if isinstance(user, UserEntity) else user

    await store_thumbnail(
        project_name,
        thumbnail_id,
        pvw_bytes,
        entity=entity if (entity and entity.thumbnail_id is None) else None,
        user_name=user_name,
    )

    await Postgres.execute(
        f"""
        UPDATE project_{project_name}.files
        SET updated_at = NOW(), thumbnail_id = $2
        WHERE id = $1
        """,
        file_id,
        thumbnail_id,
    )

    return thumbnail_id

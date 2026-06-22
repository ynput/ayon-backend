from ayon_server.entities.user import UserEntity
from ayon_server.entities.version import VersionEntity
from ayon_server.helpers.preview import obtain_file_preview
from ayon_server.helpers.thumbnails import store_thumbnail
from ayon_server.logging import logger
from ayon_server.utils.hashing import create_uuid


async def assign_version_thumbnail_from_reviewable(
    project_name: str,
    file_id: str,
    *,
    version: str | VersionEntity,
    user: str | UserEntity | None = None,
) -> None:

    if isinstance(version, str):
        version = await VersionEntity.load(project_name, version)

    assert isinstance(version, VersionEntity), (
        "version must be a VersionEntity instance"
    )

    logger.debug(f"Assigning {version} thumbnail from reviewable {file_id}")
    pvw_bytes = await obtain_file_preview(project_name, file_id, thumbnail=True)
    user_name = user.name if isinstance(user, UserEntity) else user

    thumbnail_id = create_uuid()
    await store_thumbnail(
        project_name,
        thumbnail_id,
        pvw_bytes,
        entity=version,
        user_name=user_name,
    )

from fastapi import Query, Request

from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
    VersionID,
    XContentType,
    XFileName,
)
from ayon_server.entities.version import VersionEntity
from ayon_server.files import Storages
from ayon_server.reviewables.create_reviewable import (
    check_valid_mime,
    create_reviewable,
)
from ayon_server.reviewables.models import ReviewableModel
from ayon_server.utils import create_uuid

from .router import router


@router.post("/versions/{version_id}/reviewables")
async def upload_reviewable(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    sender: Sender,
    sender_type: SenderType,
    x_file_name: XFileName,
    content_type: XContentType,
    label: str | None = Query(None, description="Label", alias="label"),
) -> ReviewableModel:
    """Uploads a reviewable for a given version."""

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_create_access(user)

    file_id = create_uuid()
    check_valid_mime(content_type)

    content_disposition = f'inline; filename="{x_file_name}"'

    storage = await Storages.project(project_name)
    file_size = await storage.handle_upload(
        request,
        file_id,
        content_type=content_type,
        content_disposition=content_disposition,
    )

    return await create_reviewable(
        version,
        file_name=x_file_name,
        file_id=file_id,
        size=file_size,
        label=label,
        activity_id=None,
        content_type=content_type,
        user_name=user.name,
        sender=sender,
        sender_type=sender_type,
    )

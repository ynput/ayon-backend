import os

from fastapi import Header, Query, Request
from nxtools import logging

from ayon_server.activities.create_activity import create_activity
from ayon_server.api.dependencies import CurrentUser, ProjectName, VersionID
from ayon_server.api.files import handle_upload
from ayon_server.entities.version import VersionEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import BadRequestException
from ayon_server.helpers.ffprobe import availability_from_media_info, extract_media_info
from ayon_server.helpers.project_files import id_to_path
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid

from .common import ReviewableAuthor, ReviewableModel, ReviewableProcessingStatus
from .router import router
from .utils import is_transcoder_available


def check_valid_mime(content_type: str) -> None:
    """Checks if the content type is valid for reviewables."""
    # TODO: replace with helpers.mimetypes functions

    if content_type.lower().startswith("video/"):
        return None
    if content_type.lower() in ["application/mxf"]:
        return None
    if content_type.lower().startswith("image/"):
        return None
    raise BadRequestException("Only videos are supported for reviewables now")


@router.post("/versions/{version_id}/reviewables")
async def upload_reviewable(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    label: str | None = Query(None, description="Label", alias="label"),
    content_type: str = Header(...),
    x_file_name: str = Header(...),
    x_sender: str | None = Header(None),
) -> ReviewableModel:
    """Uploads a reviewable for a given version."""

    check_valid_mime(content_type)

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_create_access(user)

    file_id = create_uuid()
    upload_path = id_to_path(project_name, file_id)
    file_size = await handle_upload(request, upload_path)

    logging.debug(f"Uploaded file {x_file_name} ({file_size} bytes)")

    # FFProbe here

    media_info = await extract_media_info(upload_path)

    if not media_info:
        logging.warning(f"Failed to extract media info for {x_file_name}")
        try:
            os.remove(upload_path)
        except Exception:
            pass
        raise BadRequestException("Failed to extract media info")

    data = {
        "filename": x_file_name,
        "mime": content_type,
        "mediaInfo": media_info,
    }

    await Postgres.execute(
        f"""
        INSERT INTO project_{project_name}.files (id, size, author, data)
        VALUES ($1, $2, $3, $4)
        """,
        file_id,
        file_size,
        user.name,
        data,
    )

    # Create activity

    activity_id = await create_activity(
        version,
        "reviewable",
        body=f"Reviewable '{label}' uploaded",
        files=[file_id],
        data={"reviewableLabel": label},
        user_name=user.name,
    )

    summary = {
        "fileId": file_id,
        "versionId": version_id,
        "productId": version.product_id,
        "activityId": activity_id,
        "size": file_size,
        "filename": x_file_name,
        "label": label,
        "mimetype": content_type,
    }

    await EventStream.dispatch(
        "reviewable.created",
        sender=x_sender,
        user=user.name,
        project=project_name,
        summary=summary,
        description=f"Reviewable '{x_file_name}' uploaded",
    )

    availability = availability_from_media_info(media_info)

    if availability in ["unknown", "ready"]:
        processing = None
    else:
        if not await is_transcoder_available():
            processing = None
        else:
            processing = ReviewableProcessingStatus(
                event_id=None,
                status="enqueued",
                description="In a transcoder queue",
            )

    return ReviewableModel(
        file_id=file_id,
        activity_id=activity_id,
        filename=x_file_name,
        label=label,
        mimetype=content_type,
        availability=availability,
        media_info=media_info,
        created_from=None,
        processing=processing,
        author=ReviewableAuthor(name=user.name, full_name=user.attrib.fullName),
    )

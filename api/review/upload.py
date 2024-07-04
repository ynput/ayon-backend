from typing import Any

from fastapi import Header, Query, Request

from ayon_server.api.dependencies import CurrentUser, ProjectName, VersionID
from ayon_server.api.files import handle_upload
from ayon_server.entities.version import VersionEntity
from ayon_server.exceptions import BadRequestException
from ayon_server.helpers.ffprobe import ffprobe
from ayon_server.helpers.project_files import id_to_path
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid

from .router import router


async def extract_video_metadata(file_path: str) -> dict[str, Any]:
    """Extracts metadata from a video file."""

    try:
        probe_data = await ffprobe(file_path)
    except Exception:
        return {}

    return probe_data


@router.post("/versions/{version_id}/reviewables")
async def upload_reviewable(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    label: str | None = Query(None, description="Label", alias="label"),
    content_type: str = Header(...),
    x_file_name: str | None = Header(None),
) -> None:
    """Uploads a reviewable for a given version."""

    if not content_type.lower().startswith("video/"):
        raise BadRequestException("Only videos are supported for reviewables now")

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_create_access(user)

    file_id = create_uuid()
    upload_path = id_to_path(project_name, file_id)
    file_size = await handle_upload(request, upload_path)

    # FFProbe here

    data = {
        "filename": x_file_name,
        "mime": content_type,
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

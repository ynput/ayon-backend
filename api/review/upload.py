import os
from typing import Any

from fastapi import Header, Query, Request
from nxtools import logging

from ayon_server.activities.create_activity import create_activity
from ayon_server.api.dependencies import CurrentUser, ProjectName, VersionID
from ayon_server.api.files import handle_upload
from ayon_server.entities.version import VersionEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import BadRequestException
from ayon_server.helpers.ffprobe import ffprobe
from ayon_server.helpers.project_files import id_to_path
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid

from .router import router


async def extract_media_info(file_path: str) -> dict[str, Any]:
    """Extracts metadata from a video file."""

    try:
        probe_data = await ffprobe(file_path)
    except Exception:
        return {}

    result: dict[str, Any] = {
        "probeVersion": 1,
    }

    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video":
            fps_str = stream.get("r_frame_rate")
            fps_parts = fps_str.split("/")
            if len(fps_parts) == 2:
                fps = int(fps_parts[0]) / int(fps_parts[1])
            else:
                fps = float(fps_parts[0])

            result.update(
                {
                    "videoTrackIndex": stream.get("index"),
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "pixelFormat": stream.get("pix_fmt"),
                    "frameRate": fps,
                    "duration": stream.get("duration"),
                    "codec": stream.get("codec_name"),
                }
            )

        elif stream.get("codec_type") == "audio":
            if "audioTracks" not in result:
                result["audioTracks"] = []
            result["audioTracks"].append(
                {
                    "index": stream.get("index"),
                    "codec": stream.get("codec_name"),
                    "sampleRate": stream.get("sample_rate"),
                    "channels": stream.get("channels"),
                }
            )

    return result


def check_valid_mime(content_type: str) -> None:
    """Checks if the content type is valid for reviewables."""

    if content_type.lower().startswith("video/"):
        return None
    if content_type.lower() in ["application/mxf"]:
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
    x_file_name: str | None = Header(None),
    x_sender: str | None = Header(None),
) -> None:
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

    await create_activity(
        version,
        "reviewable",
        body=f"Reviewable '{label}' uploaded",
        files=[file_id],
        data={"reviewableLabel": label},
    )

    summary = {
        "fileId": file_id,
        "versionId": version_id,
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

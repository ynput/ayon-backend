import os

import aiocache
from fastapi import Header, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse

from ayon_server.api.dependencies import (
    AllowGuests,
    CurrentUser,
    FileID,
    NoTraces,
    ProjectName,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.files import Storages, create_project_file_record
from ayon_server.helpers.preview import create_video_thumbnail, get_file_preview
from ayon_server.lib.postgres import Postgres
from ayon_server.models.file_info import FileInfo
from ayon_server.types import Field, OPModel
from ayon_server.utils import create_uuid

from .router import router
from .video import serve_video


class CreateFileResponseModel(OPModel):
    id: str = Field(..., example="123")


@router.post("", status_code=201, dependencies=[AllowGuests])
async def upload_project_file(
    project_name: ProjectName,
    request: Request,
    user: CurrentUser,
    x_file_id: str | None = Header(None),
    x_file_name: str = Header(...),
    x_activity_id: str | None = Header(None),
    content_type: str = Header(...),
) -> CreateFileResponseModel:
    """Handle uploading a file to a project.

    Used for comment attachments, etc.
    Files are stored in the `uploads` directory (defined in ayon config).
    Each file is associated with its author, project and optionally an activity.

    The request accepts additional headers for the file metadata:
    - `Content-Type`: The MIME type of the file (required)
    - `X-File-Id`: The ID of the file (optional, will be generated if not provided)
    - `X-File-Name`: The name of the file including the extension (required)
    - `X-Activity-Id`: The ID of the activity the file is associated with (optional)

    """

    await user.ensure_project_access(project_name)

    if x_file_id:
        file_id = x_file_id.replace("-", "")
        if len(file_id) != 32:
            raise BadRequestException("Invalid file ID")
    else:
        file_id = create_uuid()

    async with Postgres.transaction():
        await create_project_file_record(
            project_name,
            x_file_name,
            size=0,
            content_type=content_type,
            file_id=file_id,
            user_name=user.name,
            activity_id=x_activity_id,
        )
        content_disposition = f'inline; filename="{x_file_name}"'

        storage = await Storages.project(project_name)
        file_size = await storage.handle_upload(
            request,
            file_id,
            content_type=content_type,
            content_disposition=content_disposition,
        )

        await Postgres.execute(
            f"""
            UPDATE project_{project_name}.files
            SET size = $1
            WHERE id = $2
            """,
            file_size,
            file_id,
        )

    return CreateFileResponseModel(id=file_id)


@router.delete("/{file_id}", dependencies=[AllowGuests])
async def delete_project_file(
    project_name: ProjectName,
    file_id: FileID,
    user: CurrentUser,
) -> EmptyResponse:
    await user.ensure_project_access(project_name)

    res = await Postgres.fetch(
        f"""
        SELECT author FROM project_{project_name}.files
        WHERE id = $1
        """,
        file_id,
    )

    if not res:
        raise NotFoundException("File not found")

    if not user.is_manager and res[0]["author"] != user.name:
        raise ForbiddenException("User does not have permission to delete the file")

    storage = await Storages.project(project_name)
    await storage.delete_file(file_id)

    return EmptyResponse()


@aiocache.cached(ttl=20)
async def get_file_headers(project_name: str, file_id: str) -> dict[str, str]:
    res = await Postgres.fetch(
        f"""
        SELECT size, data FROM project_{project_name}.files
        WHERE id = $1
        """,
        file_id,
    )
    if not res:
        raise NotFoundException("File not found")

    data = res[0]["data"]
    headers = {
        "Content-Length": str(res[0]["size"]),
        "Content-Type": data["mime"],
        "Content-Disposition": f'inline; filename="{data["filename"]}"',
    }
    if data.get("ynputShared"):
        headers["X-Ynput-Shared"] = "1"
    return headers


@router.head("/{file_id}", dependencies=[AllowGuests, NoTraces])
async def get_project_file_head(
    project_name: ProjectName,
    file_id: FileID,
    user: CurrentUser,
) -> Response:
    await user.ensure_project_access(project_name)
    headers = await get_file_headers(project_name, file_id)
    return Response(
        None,
        status_code=200,
        headers=headers,
    )


@router.get("/{file_id}", response_model=None, dependencies=[AllowGuests, NoTraces])
async def get_project_file(
    project_name: ProjectName,
    file_id: FileID,
    user: CurrentUser,
) -> FileResponse | Response:
    """Get a project file (comment attachment etc.)

    The `preview` query parameter can be used to get
    a preview of the file (if available).
    """

    await user.ensure_project_access(project_name)

    storage = await Storages.project(project_name)
    headers = await get_file_headers(project_name, file_id)
    ynput_shared = bool(headers.get("X-Ynput-Shared"))

    if storage.cdn_resolver is not None:
        return await storage.get_cdn_link(file_id, ynput_shared=ynput_shared)

    if storage.storage_type == "s3":
        url = await storage.get_signed_url(
            file_id,
            ttl=3600,
            content_type=headers.get("Content-Type"),
            content_disposition=headers.get("Content-Disposition"),
        )
        return RedirectResponse(url=url, status_code=302)

    url = f"/api/projects/{project_name}/files/{file_id}/payload"
    return RedirectResponse(url=url, status_code=302)


@router.get("/{file_id}/info", response_model=FileInfo, dependencies=[AllowGuests])
async def get_project_file_info(
    project_name: ProjectName,
    file_id: FileID,
    user: CurrentUser,
) -> FileInfo:
    """Get a project file (comment attachment etc.)

    The `preview` query parameter can be used to get
    a preview of the file (if available).
    """

    await user.ensure_project_access(project_name)

    storage = await Storages.project(project_name)
    return await storage.get_file_info(file_id)


@router.get(
    "/{file_id}/payload",
    response_model=None,
    dependencies=[AllowGuests, NoTraces],
)
async def get_project_file_payload(
    request: Request,
    project_name: ProjectName,
    file_id: FileID,
    user: CurrentUser,
) -> FileResponse | Response:
    storage = await Storages.project(project_name)
    if storage.storage_type != "local":
        raise BadRequestException("File storage is not local")

    path = await storage.get_path(file_id)
    if not os.path.isfile(path):
        raise NotFoundException("File not found")

    await user.ensure_project_access(project_name)
    headers = await get_file_headers(project_name, file_id)

    if headers["Content-Type"].startswith("video"):
        return await serve_video(request, path, content_type=headers["Content-Type"])

    return FileResponse(path, headers=headers)


@router.get(
    "/{file_id}/thumbnail",
    response_model=None,
    dependencies=[AllowGuests, NoTraces],
)
async def get_project_file_thumbnail(
    project_name: ProjectName,
    file_id: FileID,
    user: CurrentUser,
) -> FileResponse | Response:
    """Get a project file (comment attachment etc.)

    The `preview` query parameter can be used to get
    a preview of the file (if available).
    """

    await user.ensure_project_access(project_name)

    return await get_file_preview(project_name, file_id)


@router.get(
    "/{file_id}/still",
    response_model=None,
    dependencies=[AllowGuests, NoTraces],
)
async def get_project_file_still(
    project_name: ProjectName,
    file_id: FileID,
    user: CurrentUser,
    timestamp: float = Query(0.0, alias="t"),
) -> Response:
    """Get a still frame from a video file.

    The `t` query parameter can be used to specify the time in seconds.
    """

    await user.ensure_project_access(project_name)

    storage = await Storages.project(project_name)

    if storage.storage_type == "local":
        path = await storage.get_path(file_id)

        if not os.path.isfile(path):
            raise NotFoundException("file not found")

    elif storage.storage_type == "s3":
        path = await storage.get_signed_url(file_id)

    else:
        # Should not happen, but just in case
        raise BadRequestException("File storage is not supported")

    b = await create_video_thumbnail(path, None, timestamp)

    if b == b"":
        raise NotFoundException("No still frame available")

    return Response(b, media_type="image/jpeg")

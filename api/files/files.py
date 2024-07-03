import os

import aiocache
from fastapi import Header, Request, Response
from starlette.responses import FileResponse

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.api.files import handle_upload
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.helpers.project_files import id_to_path
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils import create_uuid

from .preview import get_file_preview, uncache_file_preview
from .router import router
from .video import serve_video


def check_user_access(project_name: ProjectName, user: CurrentUser) -> None:
    if not user.is_manager:
        if project_name not in user.data.get("accessGroups", {}):
            raise BadRequestException("User does not have access to the project")


class CreateFileResponseModel(OPModel):
    id: str = Field(..., example="123")


@router.post("", status_code=201)
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

    check_user_access(project_name, user)

    if x_file_id:
        file_id = x_file_id.replace("-", "")
        if len(file_id) != 32:
            raise BadRequestException("Invalid file ID")
    else:
        file_id = create_uuid()

    path = id_to_path(project_name, file_id)

    try:
        file_size = await handle_upload(request, path)
    except Exception as e:
        try:
            os.remove(path)
        except Exception:
            pass
        raise BadRequestException(f"Failed to upload file: {e}") from e

    data = {
        "filename": x_file_name,
        "mime": content_type,
    }

    await Postgres.execute(
        f"""
        INSERT INTO project_{project_name}.files (id, size, author, activity_id, data)
        VALUES ($1, $2, $3, $4, $5)
        """,
        file_id,
        file_size,
        user.name,
        x_activity_id,
        data,
    )

    return CreateFileResponseModel(id=file_id)


@router.delete("/{file_id}")
async def delete_project_file(
    project_name: ProjectName,
    file_id: str,
    user: CurrentUser,
) -> EmptyResponse:
    check_user_access(project_name, user)

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

    path = id_to_path(project_name, file_id)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

    await Postgres.execute(
        f"""
        DELETE FROM project_{project_name}.files
        WHERE id = $1
        """,
        file_id,
    )

    await uncache_file_preview(project_name, file_id)

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
    return headers


@router.head("/{file_id}")
async def get_project_file_head(
    project_name: ProjectName,
    file_id: str,
    user: CurrentUser,
) -> Response:
    check_user_access(project_name, user)
    headers = await get_file_headers(project_name, file_id)
    return Response(
        None,
        status_code=200,
        headers=headers,
    )


@router.get("/{file_id}", response_model=None)
async def get_project_file(
    request: Request,
    project_name: ProjectName,
    file_id: str,
    user: CurrentUser,
) -> FileResponse | Response:
    """Get a project file (comment attachment etc.)

    The `preview` query parameter can be used to get
    a preview of the file (if available).
    """

    check_user_access(project_name, user)

    path = id_to_path(project_name, file_id)

    headers = await get_file_headers(project_name, file_id)

    if headers["Content-Type"].startswith("video"):
        return await serve_video(request, path)

    return FileResponse(path, headers=headers)


@router.get("/{file_id}/thumbnail", response_model=None)
async def get_project_file_thumbnail(
    project_name: ProjectName,
    file_id: str,
    user: CurrentUser,
) -> FileResponse | Response:
    """Get a project file (comment attachment etc.)

    The `preview` query parameter can be used to get
    a preview of the file (if available).
    """

    check_user_access(project_name, user)

    return await get_file_preview(project_name, file_id)

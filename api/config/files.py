import os
from typing import Any, Literal

from fastapi import Header, Path, Request
from fastapi.responses import FileResponse

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.files import handle_upload
from ayon_server.config.serverconfig import get_server_config, save_server_config_data
from ayon_server.exceptions import BadRequestException, ForbiddenException

from .router import router

#
# Server files (login background, etc.)
#

ServerFileType = Literal["login_background", "studio_logo"]


server_files: dict[ServerFileType, dict[str, Any]] = {
    "login_background": {
        "description": "The background image displayed on the login page.",
        "example": "background.jpg",
        "mime_types": ["image/jpeg", "image/png"],
        "directory": "/storage/static/customization",
    },
    "studio_logo": {
        "description": "The logo displayed on the login page.",
        "example": "logo.png",
        "mime_types": ["image/jpeg", "image/png"],
        "directory": "/storage/static/customization",
    },
}


@router.put("/config/files/{file_type}")
async def upload_server_config_file(
    request: Request,
    user: CurrentUser,
    file_type: ServerFileType = Path(
        ...,
        description="The type of file to upload.",
        example="login_background",
    ),
    x_file_name: str = Header(
        ...,
        description="The name of the file.",
        example="background.jpg",
        regex=r"^[a-zA-Z0-9._-]+$",
    ),
    content_type: str = Header(
        ...,
        example="image/jpeg",
        regex=r"^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$",
    ),
):
    """Upload a file to the server configuration."""

    if not user.is_admin:
        raise ForbiddenException(
            "Only administrators can set server configuration values."
        )

    if file_type not in server_files:
        raise BadRequestException("Invalid file type.")

    if content_type.lower() not in server_files[file_type]["mime_types"]:
        raise BadRequestException("Invalid content type.")

    target_path = os.path.join(server_files[file_type]["directory"], x_file_name)
    await handle_upload(request, target_path)

    config = await get_server_config()
    config_data = config.dict()
    if "customization" not in config_data:
        config_data["customization"] = {}
    config_data["customization"][file_type] = x_file_name

    await save_server_config_data(config_data)


@router.get("/config/files/{file_type}")
async def get_server_config_file(user: CurrentUser, file_type: ServerFileType):
    """Get a file from the server configuration."""

    if not user.is_admin:
        raise ForbiddenException(
            "Only administrators can set server configuration values."
        )

    if file_type not in server_files:
        raise BadRequestException("Invalid file type.")

    config = await get_server_config()
    customization = config.customization
    file_name = customization.__getattribute__(file_type)
    if not file_name:
        raise BadRequestException("No file set for this type.")

    target_path = os.path.join(server_files[file_type]["directory"], file_name)
    return FileResponse(target_path)

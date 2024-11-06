from typing import Any, Literal

from fastapi import Header

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException

from .router import router

#
# Server files (login background, etc.)
#

ServerFileType = Literal["login-background", "studio-logo"]


server_files: dict[ServerFileType, dict[str, Any]] = {
    "login-background": {
        "description": "The background image displayed on the login page.",
        "example": "background.jpg",
        "mime_types": ["image/jpeg", "image/png"],
        "directory": "/storage/static/customization",
    },
    "studio-logo": {
        "description": "The logo displayed on the login page.",
        "example": "logo.png",
        "mime_types": ["image/jpeg", "image/png"],
        "directory": "/storage/static/customization",
    },
}


@router.put("/config/files/{file_id}")
async def upload_server_config_file(
    user: CurrentUser,
    file_type: ServerFileType,
    x_file_name: str = Header(...),
):
    """Upload a file to the server configuration."""

    if not user.is_admin:
        raise ForbiddenException(
            "Only administrators can set server configuration values."
        )

    pass


@router.get("/config/files/{file_id}")
async def get_server_config_file(
    user: CurrentUser,
    file_type: ServerFileType,
    x_file_name: str = Header(...),
):
    """Get a file from the server configuration."""

    if not user.is_admin:
        raise ForbiddenException(
            "Only administrators can set server configuration values."
        )

    pass

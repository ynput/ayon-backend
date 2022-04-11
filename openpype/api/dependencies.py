"""Request dependencies."""

from fastapi import Depends, Header, Path

from openpype.auth.session import Session
from openpype.entities import UserEntity
from openpype.exceptions import (
    BadRequestException,
    UnauthorizedException,
    UnsupportedMediaException,
)
from openpype.lib.redis import Redis
from openpype.utils import EntityID, parse_access_token


async def dep_access_token(authorization: str = Header(None)) -> str:
    """Parse and return an access token provided in the authorisation header"""
    access_token = parse_access_token(authorization)
    if not access_token:
        raise UnauthorizedException(log=False)
    return access_token


async def dep_thumbnail_content_type(content_type: str = Header(None)) -> str:
    content_type = content_type.lower()
    if content_type not in ["image/png", "image/jpeg"]:
        raise UnsupportedMediaException("Thumbnail must be in png or jpeg format")
    return content_type


async def dep_current_user(
    x_forwarded_for: str = Header(None, include_in_schema=False),
    access_token: str = Depends(dep_access_token),
) -> UserEntity:
    """Return the currently logged-in user

    Use `dep_access_token` to ensure a valid access token is provided
    in the authorization header and return the user associated with it.

    This is used as a dependency in the API for all endpoints that
    require authentication.
    """

    session_data = await Session.check(access_token, x_forwarded_for)
    if not session_data:
        raise UnauthorizedException("Invalid access token", log=False)
    await Redis.incr("user-requests", session_data.user.name)
    return UserEntity.from_record(session_data.user.dict())


async def dep_project_name(
    project_name: str = Path(
        ...,
        title="User name",
        regex=r"^[0-9a-zA-Z_]*$",
    )
) -> str:
    """Validate a project name specified in an endpoint path"""
    return project_name.lower()


async def dep_user_name(
    user_name: str = Path(
        ...,
        title="User name",
        regex=r"^[0-9a-zA-Z_]*$",
    )
) -> str:
    """Validate a user name specified in an endpoint path"""
    return user_name


async def dep_role_name(
    role_name: str = Path(
        ...,
        title="Role name",
        regex=r"^[0-9a-zA-Z_]*$",
    )
) -> str:
    """Validate a role name specified in an endpoint path"""
    return role_name


async def dep_folder_id(
    folder_id: str = Path(..., title="Folder ID", **EntityID.META)
) -> str:
    """Validate a folder id specified in an endpoint path."""
    return folder_id


async def dep_subset_id(
    subset_id: str = Path(..., title="Subset ID", **EntityID.META)
) -> str:
    """Validate a subset id specified in an endpoint path."""
    return subset_id


async def dep_version_id(
    version_id: str = Path(..., title="Version ID", **EntityID.META)
) -> str:
    """Validate a version id specified in an endpoint path."""
    return version_id


async def dep_representation_id(
    representation_id: str = Path(..., title="Version ID", **EntityID.META)
) -> str:
    """Validate a representation id specified in an endpoint path."""
    return representation_id


async def dep_task_id(
    task_id: str = Path(..., title="Task ID", **EntityID.META)
) -> str:
    """Validate a task id specified in an endpoint path."""
    return task_id


async def dep_link_id(
    link_id: str = Path(..., title="Link ID", **EntityID.META)
) -> str:
    """Validate a link id specified in an endpoint path."""
    return link_id


async def dep_link_type(
    link_type: str = Path(..., title="Link Type"),
) -> tuple[str, str, str]:
    try:
        name, input_type, output_type = link_type.split("|")
    except ValueError:
        raise BadRequestException(
            "Link type must be in the format 'name|input_type|output_type'"
        )

    if input_type not in ["folder", "subset", "version", "representation", "task"]:
        raise BadRequestException(
            "Link type input type must be one of 'folder', "
            "'subset', 'version', 'representation', or 'task'"
        )
    if output_type not in ["folder", "subset", "version", "representation", "task"]:
        raise BadRequestException(
            "Link type output type must be one of 'folder', "
            "'subset', 'version', 'representation', or 'task'"
        )

    return (name, input_type, output_type)

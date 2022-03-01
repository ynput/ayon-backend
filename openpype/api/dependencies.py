"""Request dependencies."""

from fastapi import Depends, Header, Path

from openpype.auth.session import Session
from openpype.entities import UserEntity
from openpype.lib.redis import Redis
from openpype.utils import EntityID, parse_access_token
from openpype.exceptions import UnauthorizedException


async def dep_access_token(authorization: str = Header(None)) -> str:
    """Parse and return an access token provided in the authorisation header"""
    access_token = parse_access_token(authorization)
    if not access_token:
        raise UnauthorizedException(log=False)
    return access_token


async def dep_current_user(
    x_forwarded_for: str = Header(None), access_token: str = Depends(dep_access_token)
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
    return UserEntity(exists=True, **session_data.user.dict())


async def dep_project_name(
    project_name: str = Path(
        ...,
        title="Project ID",
        regex=r"^[0-9a-zA-Z_]*$",
    )
) -> str:
    """Validate a project name specified in an endpoint path"""
    return project_name


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

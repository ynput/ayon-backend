"""Request dependencies."""

from fastapi import Depends, Header, Path, Request

from ayon_server.auth.session import Session
from ayon_server.auth.utils import hash_password
from ayon_server.entities import UserEntity
from ayon_server.exceptions import (
    BadRequestException,
    NotFoundException,
    UnauthorizedException,
    UnsupportedMediaException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import USER_NAME_REGEX
from ayon_server.utils import (
    EntityID,
    json_dumps,
    json_loads,
    parse_access_token,
    parse_api_key,
)


async def dep_access_token(authorization: str = Header(None)) -> str | None:
    """Parse and return an access token provided in the authorisation header."""
    access_token = parse_access_token(authorization)
    return access_token


async def dep_api_key(authorization: str = Header(None)) -> str | None:
    """Parse and return an api key provided in the authorisation header."""
    api_key = parse_api_key(authorization)
    return api_key


async def dep_thumbnail_content_type(content_type: str = Header(None)) -> str:
    """Return the mime type of the thumbnail.

    Raise an `UnsupportedMediaException` if the content type is not supported.
    """
    content_type = content_type.lower()
    if content_type not in ["image/png", "image/jpeg"]:
        raise UnsupportedMediaException("Thumbnail must be in png or jpeg format")
    return content_type


async def dep_current_user(
    request: Request,
    x_forwarded_for: str = Header(None, include_in_schema=False),
    x_as_user: str | None = Header(None),  # TODO: at least validate against a regex
    x_api_key: str | None = Header(None),  # TODO: some validation here
    access_token: str | None = Depends(dep_access_token),
    api_key: str | None = Depends(dep_api_key),
) -> UserEntity:
    """Return the currently logged-in user.

    Use `dep_access_token` to ensure a valid access token is provided
    in the authorization header and return the user associated with it.

    This is used as a dependency in the API for all endpoints that
    require authentication.

    Raise an `UnauthorizedException` if the access token is invalid,
    or the user is not permitted to access the endpoint.
    """

    if api_key := x_api_key or api_key:
        hashed_key = hash_password(api_key)
        if (session_data := await Session.check(api_key, x_forwarded_for)) is None:
            result = await Postgres.fetch(
                "SELECT * FROM users WHERE data->>'apiKey' = $1 LIMIT 1",
                hashed_key,
            )
            if not result:
                raise UnauthorizedException(
                    f"Invalid API key {hashed_key}",
                )
            user = UserEntity.from_record(result[0])
            session_data = await Session.create(user, x_forwarded_for, token=api_key)

    elif access_token is None:
        raise UnauthorizedException("Access token is missing")
    else:
        session_data = await Session.check(access_token, x_forwarded_for)

    if not session_data:
        raise UnauthorizedException("Invalid access token")
    await Redis.incr("user-requests", session_data.user.name)
    user = UserEntity.from_record(session_data.user.dict())

    if x_as_user is not None and user.is_service:
        # sudo :)
        user = await UserEntity.load(x_as_user)

    endpoint = request.scope["endpoint"].__name__
    project_name = request.path_params.get("project_name")
    if not user.is_manager:
        perms = user.permissions(project_name)
        if (perms is not None) and perms.endpoints.enabled:
            if endpoint not in perms.endpoints.endpoints:
                raise UnauthorizedException(f"{endpoint} is not accessible")
    return user


async def dep_current_user_optional(
    request: Request,
    x_forwarded_for: str = Header(None, include_in_schema=False),
    x_as_user: str | None = Header(None),  # TODO: at least validate against a regex
    x_api_key: str | None = Header(None),  # TODO: some validation here
    access_token: str | None = Depends(dep_access_token),
    api_key: str | None = Depends(dep_api_key),
) -> UserEntity | None:
    try:
        user = await dep_current_user(
            request=request,
            x_forwarded_for=x_forwarded_for,
            x_as_user=x_as_user,
            x_api_key=x_api_key,
            access_token=access_token,
            api_key=api_key,
        )
    except UnauthorizedException:
        return None
    return user


async def dep_attribute_name(
    attribute_name: str = Path(
        ...,
        title="Attribute name",
        regex=r"^[0-9a-zA-Z_]*$",
    )
) -> str:
    return attribute_name


async def dep_new_project_name(
    project_name: str = Path(
        ...,
        title="Project name",
        regex=r"^[0-9a-zA-Z_]*$",
    )
) -> str:
    """Validate and return a project name.

    This only validate the regex and does not care whether
    the project already exists, so it is used in [PUT] /projects
    request to create a new project.
    """
    return project_name


async def dep_project_name(
    project_name: str = Path(
        ...,
        title="Project name",
        regex=r"^[0-9a-zA-Z_]*$",
    )
) -> str:
    """Validate and return a project name specified in an endpoint path.

    This dependecy actually validates whether the project exists.
    If the name is specified using wrong letter case, it is corrected
    to match the database record.
    """
    if project_name == "_":
        # Wildcard project name
        return project_name

    project_list: list[str]
    project_list_data = await Redis.get("global", "project_list")
    if project_list_data:
        project_list = json_loads(project_list_data)
        for pn in project_list:
            if project_name.lower() == pn.lower():
                return pn
    project_list = [
        row["name"] async for row in Postgres.iterate("SELECT name FROM projects")
    ]
    await Redis.set("global", "project_list", json_dumps(project_list))
    for pn in project_list:
        if project_name.lower() == pn.lower():
            return pn
    raise NotFoundException(f"Project {project_name} not found")


async def dep_user_name(
    user_name: str = Path(..., title="User name", regex=USER_NAME_REGEX)
) -> str:
    """Validate and return a user name specified in an endpoint path."""
    return user_name


async def dep_role_name(
    role_name: str = Path(
        ...,
        title="Role name",
        regex=r"^[0-9a-zA-Z_]*$",
    )
) -> str:
    """Validate and return a role name specified in an endpoint path."""
    return role_name


async def dep_folder_id(
    folder_id: str = Path(..., title="Folder ID", **EntityID.META)
) -> str:
    """Validate and return a folder id specified in an endpoint path."""
    return folder_id


async def dep_subset_id(
    subset_id: str = Path(..., title="Subset ID", **EntityID.META)
) -> str:
    """Validate and return a subset id specified in an endpoint path."""
    return subset_id


async def dep_version_id(
    version_id: str = Path(..., title="Version ID", **EntityID.META)
) -> str:
    """Validate and return  a version id specified in an endpoint path."""
    return version_id


async def dep_representation_id(
    representation_id: str = Path(..., title="Version ID", **EntityID.META)
) -> str:
    """Validate and return a representation id specified in an endpoint path."""
    return representation_id


async def dep_task_id(
    task_id: str = Path(..., title="Task ID", **EntityID.META)
) -> str:
    """Validate and return a task id specified in an endpoint path."""
    return task_id


async def dep_workfile_id(
    workfile_id: str = Path(..., title="Workfile ID", **EntityID.META)
) -> str:
    """Validate and return a workfile id specified in an endpoint path."""
    return workfile_id


async def dep_thumbnail_id(
    thumbnail_id: str = Path(..., title="Thumbnail ID", **EntityID.META)
) -> str:
    """Validate and return a thumbnail id specified in an endpoint path."""
    return thumbnail_id


async def dep_event_id(
    event_id: str = Path(..., title="Event ID", **EntityID.META)
) -> str:
    """Validate and return a event id specified in an endpoint path."""
    return event_id


async def dep_link_id(
    link_id: str = Path(..., title="Link ID", **EntityID.META)
) -> str:
    """Validate and return a link id specified in an endpoint path."""
    return link_id


async def dep_link_type(
    link_type: str = Path(..., title="Link Type"),
) -> tuple[str, str, str]:
    """Validate and return a link type specified in an endpoint path.

    Return type is a tuple of (link_type, input_type, output_type)
    """
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
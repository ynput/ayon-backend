"""Request dependencies."""

from typing import Annotated

from fastapi import Depends, Header, Path, Query, Request

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
from ayon_server.types import NAME_REGEX, USER_NAME_REGEX
from ayon_server.utils import (
    EntityID,
    json_dumps,
    json_loads,
    parse_access_token,
    parse_api_key,
)


async def dep_access_token(
    authorization: str | None = Header(None),
    token: str | None = Query(None),
) -> str | None:
    """Parse and return an access token provided in the authorisation header."""
    if authorization is not None:
        return parse_access_token(authorization)
    elif token is not None:
        return token
    else:
        return None


AccessToken = Annotated[str, Depends(dep_access_token)]


async def dep_api_key(authorization: str = Header(None)) -> str | None:
    """Parse and return an api key provided in the authorisation header."""
    api_key = parse_api_key(authorization)
    return api_key


ApiKey = Annotated[str, Depends(dep_api_key)]


async def dep_thumbnail_content_type(content_type: str = Header(None)) -> str:
    """Return the mime type of the thumbnail.

    Raise an `UnsupportedMediaException` if the content type is not supported.
    """
    content_type = content_type.lower()
    if content_type not in ["image/png", "image/jpeg"]:
        raise UnsupportedMediaException("Thumbnail must be in png or jpeg format")
    return content_type


ThumbnailContentType = Annotated[str, Depends(dep_thumbnail_content_type)]


async def dep_current_user(
    request: Request,
    x_as_user: str | None = Header(None, regex=USER_NAME_REGEX),
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
        if (session_data := await Session.check(api_key, request)) is None:
            result = await Postgres.fetch(
                "SELECT * FROM users WHERE data->>'apiKey' = $1 LIMIT 1",
                hashed_key,
            )
            if not result:
                raise UnauthorizedException(
                    f"Invalid API key {hashed_key}",
                )
            user = UserEntity.from_record(result[0])
            session_data = await Session.create(user, request, token=api_key)

    elif access_token is None:
        raise UnauthorizedException("Access token is missing")
    else:
        session_data = await Session.check(access_token, request)

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


CurrentUser = Annotated[UserEntity, Depends(dep_current_user)]


async def dep_current_user_optional(
    request: Request,
    x_as_user: str | None = Header(None, regex=USER_NAME_REGEX),
    x_api_key: str | None = Header(None),  # TODO: some validation here
    access_token: str | None = Depends(dep_access_token),
    api_key: str | None = Depends(dep_api_key),
) -> UserEntity | None:
    try:
        user = await dep_current_user(
            request=request,
            x_as_user=x_as_user,
            x_api_key=x_api_key,
            access_token=access_token,
            api_key=api_key,
        )
    except UnauthorizedException:
        return None
    return user


CurrentUserOptional = Annotated[UserEntity | None, Depends(dep_current_user_optional)]


async def dep_attribute_name(
    attribute_name: str = Path(
        ...,
        title="Attribute name",
        regex=NAME_REGEX,
    )
) -> str:
    return attribute_name


AttributeName = Annotated[str, Depends(dep_attribute_name)]


async def dep_new_project_name(
    project_name: str = Path(
        ...,
        title="Project name",
        regex=NAME_REGEX,
    )
) -> str:
    """Validate and return a project name.

    This only validate the regex and does not care whether
    the project already exists, so it is used in [PUT] /projects
    request to create a new project.
    """
    return project_name


NewProjectName = Annotated[str, Depends(dep_new_project_name)]


async def dep_project_name(
    project_name: str = Path(
        ...,
        title="Project name",
        regex=NAME_REGEX,
    )
) -> str:
    """Validate and return a project name specified in an endpoint path.

    This dependecy actually validates whether the project exists.
    If the name is specified using wrong letter case, it is corrected
    to match the database record.
    """

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


ProjectName = Annotated[str, Depends(dep_project_name)]


async def dep_project_name_or_underscore(
    project_name: str = Path(..., title="Project name")
) -> str:
    if project_name == "_":
        return project_name
    return await dep_project_name(project_name)


ProjectNameOrUnderscore = Annotated[str, Depends(dep_project_name_or_underscore)]


async def dep_user_name(
    user_name: str = Path(..., title="User name", regex=USER_NAME_REGEX)
) -> str:
    """Validate and return a user name specified in an endpoint path."""
    return user_name


UserName = Annotated[str, Depends(dep_user_name)]


async def dep_role_name(
    role_name: str = Path(
        ...,
        title="Role name",
        regex=NAME_REGEX,
    )
) -> str:
    """Validate and return a role name specified in an endpoint path."""
    return role_name


RoleName = Annotated[str, Depends(dep_role_name)]


async def dep_secret_name(
    secret_name: str = Path(
        ...,
        title="Secret name",
        regex=NAME_REGEX,
    )
) -> str:
    """Validate and return a secret name specified in an endpoint path."""
    return secret_name


SecretName = Annotated[str, Depends(dep_secret_name)]


async def dep_folder_id(
    folder_id: str = Path(..., title="Folder ID", **EntityID.META)
) -> str:
    """Validate and return a folder id specified in an endpoint path."""
    return folder_id


FolderID = Annotated[str, Depends(dep_folder_id)]


async def dep_product_id(
    product_id: str = Path(..., title="Product ID", **EntityID.META)
) -> str:
    """Validate and return a product id specified in an endpoint path."""
    return product_id


ProductID = Annotated[str, Depends(dep_product_id)]


async def dep_version_id(
    version_id: str = Path(..., title="Version ID", **EntityID.META)
) -> str:
    """Validate and return  a version id specified in an endpoint path."""
    return version_id


VersionID = Annotated[str, Depends(dep_version_id)]


async def dep_representation_id(
    representation_id: str = Path(..., title="Version ID", **EntityID.META)
) -> str:
    """Validate and return a representation id specified in an endpoint path."""
    return representation_id


RepresentationID = Annotated[str, Depends(dep_representation_id)]


async def dep_task_id(
    task_id: str = Path(..., title="Task ID", **EntityID.META)
) -> str:
    """Validate and return a task id specified in an endpoint path."""
    return task_id


TaskID = Annotated[str, Depends(dep_task_id)]


async def dep_workfile_id(
    workfile_id: str = Path(..., title="Workfile ID", **EntityID.META)
) -> str:
    """Validate and return a workfile id specified in an endpoint path."""
    return workfile_id


WorkfileID = Annotated[str, Depends(dep_workfile_id)]


async def dep_thumbnail_id(
    thumbnail_id: str = Path(..., title="Thumbnail ID", **EntityID.META)
) -> str:
    """Validate and return a thumbnail id specified in an endpoint path."""
    return thumbnail_id


ThumbnailID = Annotated[str, Depends(dep_thumbnail_id)]


async def dep_event_id(
    event_id: str = Path(..., title="Event ID", **EntityID.META)
) -> str:
    """Validate and return a event id specified in an endpoint path."""
    return event_id


EventID = Annotated[str, Depends(dep_event_id)]


async def dep_link_id(
    link_id: str = Path(..., title="Link ID", **EntityID.META)
) -> str:
    """Validate and return a link id specified in an endpoint path."""
    return link_id


LinkID = Annotated[str, Depends(dep_link_id)]


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
        ) from None

    if input_type not in ["folder", "product", "version", "representation", "task"]:
        raise BadRequestException(
            "Link type input type must be one of 'folder', "
            "'product', 'version', 'representation', or 'task'"
        )
    if output_type not in ["folder", "product", "version", "representation", "task"]:
        raise BadRequestException(
            "Link type output type must be one of 'folder', "
            "'product', 'version', 'representation', or 'task'"
        )

    return (name, input_type, output_type)


LinkType = Annotated[tuple[str, str, str], Depends(dep_link_type)]


async def dep_site_id(x_ayon_site_id: str = Header(..., title="Site ID")) -> str:
    """Validate and return a site id specified in an endpoint header."""
    return x_ayon_site_id


SiteID = Annotated[str, Depends(dep_site_id)]

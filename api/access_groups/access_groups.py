from typing import Any

from fastapi import APIRouter, Body
from nxtools import log_traceback

from ayon_server.access.access_groups import AccessGroups
from ayon_server.access.permissions import Permissions
from ayon_server.api.dependencies import (
    AccessGroupName,
    CurrentUser,
    ProjectNameOrUnderscore,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import (
    ConstraintViolationException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.settings.postprocess import postprocess_settings_schema

router = APIRouter(prefix="", tags=["Access Groups"])


@router.get("/roles/_schema", deprecated=True)
@router.get("/accessGroups/_schema")
async def get_access_group_schema():
    schema = Permissions.schema()
    await postprocess_settings_schema(schema, Permissions)
    return Permissions.schema()


@router.get("/roles/{project_name}", deprecated=True)
@router.get("/accessGroups/{project_name}")
async def get_access_groups(
    user: CurrentUser, project_name: ProjectNameOrUnderscore
) -> list[dict[str, Any]]:
    """Get a list of access group for a given project"""

    rdict = {}

    for role_key, _perms in AccessGroups.roles.items():
        access_group_name, pname = role_key
        if pname == "_":
            if access_group_name in rdict:
                continue
            else:
                rdict[access_group_name] = {"isProjectLevel": False}
        elif pname == project_name:
            rdict[access_group_name] = {"isProjectLevel": pname != "_"}

    result: list[dict[str, Any]] = []
    for access_group_name, data in rdict.items():
        result.append({"name": access_group_name, **data})
    result.sort(key=lambda x: x["name"])
    return result


@router.get(
    "/roles/{access_group_name}/{project_name}",
    response_model_exclude_none=True,
    deprecated=True,
)
@router.get(
    "/accessGroups/{access_group_name}/{project_name}",
    response_model_exclude_none=True,
)
async def get_role(
    user: CurrentUser,
    access_group_name: AccessGroupName,
    project_name: ProjectNameOrUnderscore,
) -> Permissions:
    """Get a role definition"""
    return AccessGroups.combine([access_group_name], project_name)


@router.put(
    "/roles/{access_group_name}/{project_name}",
    status_code=204,
    deprecated=True,
)
@router.put(
    "/accessGroups/{access_group_name}/{project_name}",
    status_code=204,
)
async def save_role(
    user: CurrentUser,
    access_group_name: AccessGroupName,
    project_name: ProjectNameOrUnderscore,
    data: Permissions = Body(..., description="Set of role permissions"),
) -> EmptyResponse:
    """Create or update a user role.

    Use `_` as a project name to save a global role.
    """

    if not user.is_manager:
        raise ForbiddenException

    scope = "public" if project_name == "_" else f"project_{project_name}"

    try:
        await Postgres.execute(
            f"""
            INSERT INTO {scope}.roles (name, data)
            VALUES ($1, $2)
            ON CONFLICT (name)
            DO UPDATE SET data = $2
            """,
            access_group_name,
            data.dict(),
        )
    except Exception:
        # TODO: which exception is raised?
        log_traceback()
        raise ConstraintViolationException(
            f"Unable to add role {access_group_name}"
        ) from None

    await AccessGroups.load()
    # TODO: messaging: notify other instances
    return EmptyResponse()


@router.delete(
    "/roles/{access_group_name}/{project_name}", status_code=204, deprecated=True
)
@router.delete("/accessGroups/{access_group_name}/{project_name}", status_code=204)
async def delete_role(
    user: CurrentUser,
    access_group_name: AccessGroupName,
    project_name: ProjectNameOrUnderscore,
):
    """Delete a user role"""

    if not user.is_manager:
        raise ForbiddenException

    if (access_group_name, project_name) not in AccessGroups.roles:
        raise NotFoundException(f"Unable to delete role {access_group_name}. Not found")

    scope = "public" if project_name == "_" else f"project_{project_name}"

    await Postgres.execute(
        f"DELETE FROM {scope}.roles WHERE name = $1",
        access_group_name,
    )

    if scope == "public":
        # TODO: Remove role records from users
        # when the default role is removed
        pass

    await AccessGroups.load()
    # TODO: messaging: notify other instances
    return EmptyResponse()

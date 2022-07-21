from fastapi import APIRouter, Body, Depends, Response
from nxtools import log_traceback

from openpype.access.permissions import Permissions
from openpype.access.roles import Roles
from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user, dep_project_name, dep_role_name
from openpype.entities import UserEntity
from openpype.exceptions import (
    ConstraintViolationException,
    ForbiddenException,
    NotFoundException,
)
from openpype.lib.postgres import Postgres

#
# Router
#


router = APIRouter(
    prefix="/roles",
    tags=["Roles"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)


#
# [GET] /api/roles/{project_name}
#


@router.get("/{project_name}")
async def get_roles(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Get a list of roles for a given project"""

    rdict = {}

    for role_key, perms in Roles.roles.items():
        role_name, pname = role_key
        if pname == "_":
            if role_name in rdict:
                continue
            else:
                rdict[role_name] = {"isProjectLevel": False}
        elif pname == project_name:
            rdict[role_name] = {"isProjectLevel": pname != "_"}

    result = []
    for role_name, data in rdict.items():
        result.append({"name": role_name, **data})
    return result


@router.get(
    "/{role_name}/{project_name}",
    response_model=Permissions,
    response_model_exclude_none=True,
)
async def get_role(
    user: UserEntity = Depends(dep_current_user),
    role_name: str = Depends(dep_role_name),
    project_name: str = Depends(dep_project_name),
):
    """Get user role information"""

    if not user.is_manager:
        raise ForbiddenException

    return Roles.combine([role_name], project_name)


@router.put(
    "/{role_name}/{project_name}",
    response_class=Response,
    status_code=201,
    responses={
        201: {"content": "", "description": "Role created"},
        409: ResponseFactory.error(409, "Role already exists"),
    },
)
async def save_role(
    data: Permissions = Body(..., description="Set of role permissions"),
    user: UserEntity = Depends(dep_current_user),
    role_name: str = Depends(dep_role_name),
    project_name: str = Depends(dep_project_name),
):
    """Create or update a user role.

    Use `_` as a project name to save a global role.
    """

    if not user.is_manager:
        raise ForbiddenException

    try:
        await Postgres.execute(
            """
            INSERT INTO public.roles (name, project_name, data)
            VALUES ($1, $2, $3)
            ON CONFLICT (name, project_name)
            DO UPDATE SET data = $3
            """,
            role_name,
            project_name,
            data.dict(),
        )
    except Exception:
        # TODO: which exception is raised?
        log_traceback()
        raise ConstraintViolationException(f"Unable to add role {role_name}")

    await Roles.load()
    # TODO: messaging: notify other instances
    return Response(status_code=201)


@router.delete(
    "/{role_name}/{project_name}",
    response_class=Response,
    status_code=204,
)
async def delete_role(
    user: UserEntity = Depends(dep_current_user),
    role_name: str = Depends(dep_role_name),
    project_name: str = Depends(dep_project_name),
):
    """Delete a user role"""

    if not user.is_manager:
        raise ForbiddenException

    if (role_name, project_name) not in Roles.roles:
        raise NotFoundException(f"Unable to delete role {role_name}. Not found")

    await Postgres.execute(
        "DELETE FROM roles WHERE name = $1 AND project_name = $2",
        role_name,
        project_name,
    )

    # TODO: Remove role records from users. Tricky.
    await Roles.load()
    # TODO: messaging: notify other instances
    return Response(status_code=204)

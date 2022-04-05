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
    RecordNotFoundException,
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
# [GET] /api/users/{username}
#


@router.get(
    "/{role_name}/{project_name}",
    operation_id="get_user_role",
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
    operation_id="create_user_role",
    response_class=Response,
    status_code=201,
    responses={
        201: {"content": "", "description": "Role created"},
        409: ResponseFactory.error(409, "Role already exists"),
    },
)
async def create_role(
    data: Permissions = Body(..., description="Set of role permissions"),
    user: UserEntity = Depends(dep_current_user),
    role_name: str = Depends(dep_role_name),
    project_name: str = Depends(dep_project_name),
):
    """Create a new user roleself.

    Use `_` as a project name to create a global role.
    """

    if not user.is_manager:
        raise ForbiddenException

    try:
        await Postgres.execute(
            """
            INSERT INTO public.roles (name, project_name, data)
            VALUES ($1, $2, $3)
            """,
            role_name,
            project_name,
            data,
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
    operation_id="delete_user_role",
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
        raise RecordNotFoundException("Unable to update role. Not found")

    await Postgres.execute(
        "DELETE FROM roles WHERE name = $1 AND project_name = $2",
        role_name,
        project_name,
    )

    # TODO: Remove role records from users. Tricky.
    await Roles.load()
    # TODO: messaging: notify other instances
    return Response(status_code=204)


@router.patch("/{role_name}/{project_name}", response_class=Response, status_code=204)
async def update_role(
    data: Permissions = Body(..., description="Set of new permissions"),
    user: UserEntity = Depends(dep_current_user),
    role_name: str = Depends(dep_role_name),
    project_name: str = Depends(dep_project_name),
):
    """Update a user role.

    Warning! This endpoint does not support partial updates.
    Always provide complete `Permissions` object.

    e.g. use [GET] /roles to obtain the original, modify it
    and store it again using the [PATCH] request.
    """

    if not user.is_manager:
        raise ForbiddenException

    if (role_name, project_name) not in Roles.roles:
        raise RecordNotFoundException("Unable to update role. Not found")

    await Postgres.execute(
        "UPDATE roles SET data=$1 WHERE name = $2 AND project_name = $3",
        data,
        role_name,
        project_name,
    )

    await Roles.load()
    # TODO: messaging: notify other instances
    return Response(status_code=204)

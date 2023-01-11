from typing import Any

from fastapi import Depends, Header, Path, Response
from projects.router import router

from ayon_server.api import ResponseFactory, dep_current_user, dep_project_name
from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.events import dispatch_event
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.deploy_project import anatomy_to_project_data
from ayon_server.lib.postgres import Postgres
from ayon_server.types import OPModel


@router.get(
    "/projects/{project_name}/roots",
    responses={404: ResponseFactory.error(404, "Project not found")},
)
async def get_project_roots_overrides(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Return overrides for project roots.

    This endpoint is used to get overrides for project roots.
    The result is an a dictionary with machine_id as a key and
    a dictionary with root names as keys and root paths as values.
    """

    query = f"SELECT machine_ident, data FROM project_{project_name}.custom_roots WHERE user_name = $1"

    result: dict[str, dict[str, str]] = {}

    async for row in Postgres.iterate(query, user.name):
        machine_ident = row["machine_ident"]
        result[machine_ident] = row["data"]

    print(result)
    return result


@router.put("/projects/{project_name}/roots/{machine_id}", response_class=Response)
async def set_project_roots_overrides(
    payload: dict[str, str],
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    machine_id: str = Path(...),
):

    project = await ProjectEntity.load(project_name)
    for root_name in project.config["roots"]:
        if root_name not in payload:
            payload.pop(root_name, None)

    query = f"""
        INSERT INTO project_{project_name}.custom_roots (machine_ident, user_name, data)
        VALUES ($1, $2, $3)
        ON CONFLICT (machine_ident, user_name) DO UPDATE SET data = $3
    """

    await Postgres.execute(query, machine_id, user.name, payload)

    return Response(status_code=204)

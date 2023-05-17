from fastapi import Path

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import ProjectEntity
from ayon_server.lib.postgres import Postgres
from projects.router import router


@router.get("/projects/{project_name}/roots")
async def get_project_roots_overrides(
    user: CurrentUser,
    project_name: ProjectName,
) -> dict[str, dict[str, str]]:
    """Return overrides for project roots.

    This endpoint is used to get overrides for project roots.
    The result is an a dictionary with site_id as a key and
    a dictionary with root names as keys and root paths as values.
    """

    query = f"""
        SELECT site_id, data
        FROM project_{project_name}.custom_roots
        WHERE user_name = $1
    """

    result: dict[str, dict[str, str]] = {}

    async for row in Postgres.iterate(query, user.name):
        site_id = row["site_id"]
        result[site_id] = row["data"]

    return result


@router.put("/projects/{project_name}/roots/{site_id}")
async def set_project_roots_overrides(
    payload: dict[str, str],
    user: CurrentUser,
    project_name: ProjectName,
    site_id: str = Path(...),
) -> EmptyResponse:

    project = await ProjectEntity.load(project_name)
    for root_name in project.config["roots"]:
        if root_name not in payload:
            payload.pop(root_name, None)

    query = f"""
        INSERT INTO project_{project_name}.custom_roots (site_id, user_name, data)
        VALUES ($1, $2, $3)
        ON CONFLICT (site_id, user_name) DO UPDATE SET data = $3
    """

    await Postgres.execute(query, site_id, user.name, payload)

    return EmptyResponse()

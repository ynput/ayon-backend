from fastapi import Path

from ayon_server.api.dependencies import ClientSiteID, CurrentUser, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import ProjectEntity
from ayon_server.helpers.roots import get_roots_for_projects
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Platform

from .router import router


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
        data = {k: v for k, v in row["data"].items() if v}
        if data:
            result[site_id] = data

    return result


@router.put("/projects/{project_name}/roots/{site_id}")
async def set_project_roots_overrides(
    payload: dict[str, str | None],
    user: CurrentUser,
    project_name: ProjectName,
    site_id: str = Path(...),
) -> EmptyResponse:
    """Set overrides for project roots."""

    project = await ProjectEntity.load(project_name)
    for root_name in project.config["roots"]:
        if root_name not in payload:
            payload.pop(root_name, None)
        elif not payload.get(root_name):
            payload.pop(root_name, None)

    if payload:
        query = f"""
            INSERT INTO project_{project_name}.custom_roots (site_id, user_name, data)
            VALUES ($1, $2, $3)
            ON CONFLICT (site_id, user_name) DO UPDATE SET data = $3
        """

        await Postgres.execute(query, site_id, user.name, payload)
    else:
        query = f"""
            DELETE FROM project_{project_name}.custom_roots
            WHERE site_id = $1 AND user_name = $2
        """

        await Postgres.execute(query, site_id, user.name)

    return EmptyResponse()


@router.get("/projects/{project_name}/siteRoots")
async def get_project_site_roots(
    project_name: ProjectName,
    user: CurrentUser,
    site_id: ClientSiteID,
    platform: Platform | None = None,
) -> dict[str, str]:
    """Return roots for a project on a specific site.

    Thist takes in account roots declared in the project anatomy
    as well as site overrides. The result is combined and returned
    as a dictionary with root names as keys and root paths as values.

    As the site also defines the platform, the result is specific to
    the platform of the site.
    """

    all_roots = await get_roots_for_projects(
        user.name,
        site_id,
        [project_name],
        platform,
    )
    return all_roots[project_name]

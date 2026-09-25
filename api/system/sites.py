from typing import Annotated

from fastapi import BackgroundTasks, Path, Query

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel, Platform

from .router import router


class SiteInfo(OPModel):
    id: str = Field(..., title="Site identifier")
    platform: Platform = Field(...)
    hostname: str = Field(..., title="Machine hostname")
    version: str = Field(..., title="Ayon version")
    users: set[str] = Field(..., title="List of users")


@router.get("/system/sites")
async def get_sites(
    user: CurrentUser,
    platform: Platform | None = Query(None),
    hostname: str | None = Query(None),
) -> list[SiteInfo]:
    """Get list of sites"""

    result: list[SiteInfo] = []
    query = "SELECT id, data FROM sites"
    async for row in Postgres.iterate(query):
        site = SiteInfo(id=row["id"], **row["data"])

        if platform and site.platform != platform:
            continue

        if hostname and site.hostname != hostname:
            continue

        if user.name not in site.users and (not user.is_manager):
            continue

        result.append(site)

    return result


async def _post_site_delete(site_id: str) -> None:
    """Delete site-related data after site deletion"""

    projects = await get_project_list()
    for project in projects:
        async with Postgres.transaction():
            await Postgres.set_project_schema(project.name)
            q = """
                DELETE FROM project_site_settings
                WHERE site_id = $1
            """

            await Postgres.execute(q, site_id)

            q = """
                DELETE FROM custom_roots
                WHERE site_id = $1
            """

            await Postgres.execute(q, site_id)


@router.delete("/system/sites/{site_id}")
async def delete_site(
    site_id: Annotated[
        str,
        Path(
            ...,
            title="Site identifier",
            regex="^[a-zA-Z0-9_-]+$",
        ),
    ],
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EmptyResponse:
    """Unregister a site by its ID"""

    if not user.is_admin:
        raise ForbiddenException("Only administrators can delete sites")

    query = """
        WITH deleted AS (
            DELETE FROM sites
            WHERE id = $1
            RETURNING id, data
        )
        SELECT id, data FROM deleted
    """

    row = await Postgres.fetchrow(query, site_id)
    if not row:
        raise NotFoundException("Site not found")

    background_tasks.add_task(_post_site_delete, site_id)

    return EmptyResponse()

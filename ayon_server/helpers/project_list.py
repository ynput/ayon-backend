from datetime import datetime
from typing import Any

from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import OPModel
from ayon_server.utils import get_nickname, json_dumps, json_loads


class ProjectListItem(OPModel):
    name: str
    code: str
    active: bool = True
    created_at: datetime
    nickname: str
    role: str | None = None


async def build_project_list() -> list[ProjectListItem]:
    q = """
        SELECT
            name,
            code,
            active,
            created_at,
            data->>'projectRole' as role
        FROM public.projects ORDER BY name ASC
    """
    result: list[dict[str, Any]] = []
    try:
        async for row in Postgres.iterate(q):
            result.append(
                {
                    "name": row["name"],
                    "code": row["code"],
                    "active": row["active"],
                    "created_at": row["created_at"],
                    "nickname": get_nickname(str(row["created_at"]) + row["name"], 2),
                    "role": row["role"],
                }
            )
    except Postgres.UndefinedTableError:
        # No projects table, return an empty list
        pass
    else:
        await Redis.set("global", "project-list", json_dumps(result))
    return [ProjectListItem(**item) for item in result]


async def get_project_list() -> list[ProjectListItem]:
    project_list = await Redis.get("global", "project-list")
    if project_list is None:
        project_list = await build_project_list()
        return project_list
    else:
        project_list = json_loads(project_list)
        return [ProjectListItem(**item) for item in project_list]


async def get_project_info(project_name: str) -> ProjectListItem:
    """Return a single project info"""
    project_list = await get_project_list()
    project_name = project_name.lower()
    for project in project_list:
        if project.name.lower() == project_name:
            return project
    raise NotFoundException(f"Project {project_name} not found")


async def normalize_project_name(project_name: str) -> str:
    """Return the canonical project name matching the input case-insensitively."""
    return (await get_project_info(project_name)).name

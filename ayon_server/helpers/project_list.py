from datetime import datetime
from typing import Any

from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import OPModel
from ayon_server.utils import get_nickname


class ProjectListItem(OPModel):
    name: str
    code: str
    label: str | None = None
    active: bool = True
    created_at: datetime
    nickname: str
    role: str | None = None
    skeleton: bool = False


async def build_project_list() -> list[ProjectListItem]:
    q = """
        SELECT
            name,
            code,
            label,
            active,
            created_at,
            data->>'projectRole' as role,
            data->>'isSkeleton' as skeleton
        FROM public.projects ORDER BY name ASC
    """
    result: list[dict[str, Any]] = []
    try:
        async for row in Postgres.iterate(q):
            result.append(
                {
                    "name": row["name"],
                    "code": row["code"],
                    "label": row["label"],
                    "active": row["active"],
                    "created_at": row["created_at"],
                    "nickname": get_nickname(str(row["created_at"]) + row["name"], 2),
                    "role": row["role"],
                    "skeleton": row["skeleton"] == "true",
                }
            )
    except Postgres.UndefinedTableError:
        # No projects table, return an empty list
        pass
    else:
        await Redis.set_json("global", "project-list", result)
    return [ProjectListItem(**item) for item in result]


async def get_project_list(
    *,
    force_load: bool = True,
    with_skeleton: bool = False,
) -> list[ProjectListItem]:
    if not force_load:
        project_list_data = await Redis.get_json("global", "project-list")
    else:
        project_list_data = None

    if project_list_data is None:
        project_list = await build_project_list()
    else:
        project_list = [ProjectListItem(**item) for item in project_list_data]

    def project_filter(p: ProjectListItem) -> bool:
        if p.skeleton and not with_skeleton:
            return False
        return True

    reduced_project_list = filter(project_filter, project_list)
    return list(reduced_project_list)


async def get_project_info(
    project_name: str,
    *,
    project_code: str | None = None,
    with_skeleton=False,
) -> ProjectListItem:
    """Return a single project info

    Retrieves the project info by name case insensitively.
    If project_code is provided, both name and code are checked for a match.
    This may be use to ensure that project name and code are unique, not
    as the mean of retrieving a single project as it is not explicit
    which project will be returned if both name and code are provided,
    but belong to different projects.
    """
    project_list = await get_project_list(with_skeleton=with_skeleton)
    project_name = project_name.lower()
    for project in project_list:
        if project.name.lower() == project_name:
            return project
        if project_code and project.code.lower() == project_code.lower():
            return project
    raise NotFoundException(f"Project {project_name} not found")


async def normalize_project_name(
    project_name: str,
    *,
    with_skeleton: bool = False,
) -> str:
    """Return the canonical project name matching the input case-insensitively."""
    return (await get_project_info(project_name, with_skeleton=with_skeleton)).name

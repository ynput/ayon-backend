import functools
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import OPModel
from ayon_server.utils import get_nickname

# Project delete/rename hold it exclusively, queries over all project schemas shared
PROJECT_SCHEMA_LOCK = 0x41594F4E


async def lock_project_schemas() -> None:
    """Wait for running cross-project queries and keep new ones out until commit."""
    assert await Postgres.is_in_transaction(), "must be called in a transaction"
    await Postgres.execute("SELECT pg_advisory_xact_lock($1)", PROJECT_SCHEMA_LOCK)


def reads_all_projects[**P, R](
    func: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    """Run a query over many project schemas without racing project deletion."""

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async with Postgres.transaction():
            await Postgres.execute(
                "SELECT pg_advisory_xact_lock_shared($1)", PROJECT_SCHEMA_LOCK
            )
            return await func(*args, **kwargs)

    return wrapper


PROJECT_LIST_REBUILD_LOCK = 0x41594F50


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
    logger.trace("Rebuilding project list cache")
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
        async with Postgres.transaction():
            # held until the cache is written, so a stale rebuild can never write last
            await Postgres.execute(
                "SELECT pg_advisory_xact_lock($1)", PROJECT_LIST_REBUILD_LOCK
            )
            stmt = await Postgres.prepare(q)
            async for row in stmt.cursor():
                result.append(
                    {
                        "name": row["name"],
                        "code": row["code"],
                        "label": row["label"],
                        "active": row["active"],
                        "created_at": row["created_at"],
                        "nickname": get_nickname(
                            str(row["created_at"]) + row["name"], 2
                        ),
                        "role": row["role"],
                        "skeleton": row["skeleton"] == "true",
                    }
                )
            await Redis.set_json("global", "project-list", result)
    except Postgres.UndefinedTableError:
        # No projects table, return an empty list
        await Redis.set_json("global", "project-list", result)
    return [ProjectListItem(**item) for item in result]


async def get_project_list(
    *,
    force_load: bool = False,
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

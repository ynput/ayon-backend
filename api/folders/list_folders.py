import datetime
import time
from typing import Any

from fastapi import Query, Response
from starlette.responses import StreamingResponse

from ayon_server.access.utils import folder_access_list
from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import OPModel
from ayon_server.utils import camelize, json_dumps, json_loads

from .router import router


class FolderListItem(OPModel):
    id: str
    path: str
    parent_id: str | None = None
    parents: list[str]
    name: str
    label: str | None = None
    folder_type: str
    has_tasks: bool = False
    has_children: bool = False
    task_names: list[str] | None
    status: str
    attrib: dict[str, Any] | None = None
    own_attrib: list[str] | None = None
    updated_at: datetime.datetime


class FolderListModel(OPModel):
    detail: str
    folders: list[FolderListItem]


async def get_entities(project_name: str) -> list[dict[str, str]]:
    entities_data = await Redis.get("project.folders", project_name)
    if entities_data is None:
        return await rebuild_hierarchy_cache(project_name)
    else:
        return json_loads(entities_data)


@router.get("", response_class=Response, responses={200: {"model": FolderListModel}})
async def get_folder_list(
    user: CurrentUser,
    project_name: ProjectName,
    attrib: bool = Query(False, description="Include folder attributes"),
):
    """Return all folders in the project. Fast.

    This is a similar endpoint to /hierarchy, but the result
    is a flat list. additionally, this endpoint should be faster
    since it uses a cache. The cache is updated every time a
    folder is created, updated, or deleted.

    The endpoint handles ACL and also returns folder attributes.
    """

    start_time = time.monotonic()

    _access_list = await folder_access_list(user, project_name, "read")
    access_list: set[str] | None = None if _access_list is None else set(_access_list)
    entities = await get_entities(project_name)

    elapsed_time = time.monotonic() - start_time
    ent_count = len(entities)
    me = f"{ent_count} folders {'with' if attrib else 'without'} attr of {project_name}"
    detail = f"{me} fetched in {elapsed_time:.3f} seconds"
    logger.trace(detail)

    camelize_memo = {}

    def camelize_memoized(src: str) -> str:
        if src not in camelize_memo:
            camelize_memo[src] = camelize(src)
        return camelize_memo[src]

    async def json_stream():
        start_time = time.monotonic()
        yield '{"folders": ['
        first = True
        for folder in entities:
            if access_list is not None and folder["path"] not in access_list:
                continue

            if not first:
                yield ","
            first = False

            if not attrib:
                folder.pop("attrib", None)
                folder.pop("own_attrib", None)

            parsed = {camelize_memoized(key): value for key, value in folder.items()}

            yield json_dumps(parsed)
        yield "]}"
        elapsed_time = time.monotonic() - start_time
        logger.trace(f"{me} streamed in {elapsed_time:.3f} seconds")

    return StreamingResponse(json_stream(), media_type="application/json")

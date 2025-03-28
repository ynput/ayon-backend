import asyncio
import datetime
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import Query, Response

from ayon_server.access.utils import AccessChecker
from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import OPModel
from ayon_server.utils import camelize, json_dumps, json_loads

from .router import router

# This model is only used for the API documentaion,
# it is not actually used in the code as we stream the json response
# that is generated on the fly.


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
    tags: list[str] | None
    status: str
    attrib: dict[str, Any] | None = None
    own_attrib: list[str] | None = None
    updated_at: datetime.datetime


class FolderListModel(OPModel):
    detail: str
    folders: list[FolderListItem]


class FolderListLoader:
    _current_futures: dict[str, asyncio.Task[list[dict[str, Any]]]]
    _lock: asyncio.Lock
    _executor: ThreadPoolExecutor

    def __init__(self):
        self._current_futures = {}
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=10)

    async def get_folder_list(self, project_name: str) -> list[dict[str, Any]]:
        async with self._lock:
            if project_name not in self._current_futures:
                self._current_futures[project_name] = asyncio.create_task(
                    self._load_folders(project_name)
                )

        data = await self._current_futures[project_name]

        async with self._lock:
            self._current_futures.pop(project_name, None)

        return data

    async def _load_folders(self, project_name: str) -> list[dict[str, Any]]:
        logger.trace(f"Loading folders for project {project_name}")
        camelize_memo = {}

        def camelize_memoized(src: str) -> str:
            if src not in camelize_memo:
                camelize_memo[src] = camelize(src)
            return camelize_memo[src]

        def process_record(record: dict[str, Any]) -> dict[str, Any]:
            return {camelize_memoized(k): v for k, v in record.items()}

        entities_data = await Redis.get("project.folders", project_name)
        if entities_data is None:
            folder_list = await rebuild_hierarchy_cache(project_name)
        else:
            folder_list = json_loads(entities_data)

        assert isinstance(folder_list, list)
        return [process_record(record) for record in folder_list]

    def _build_response(
        self,
        folder_list: list[dict[str, Any]],
        access_checker: AccessChecker,
    ) -> Response:
        return Response(
            json_dumps(
                {"folders": [r for r in folder_list if access_checker[r["path"]]]}
            ),
            media_type="application/json",
        )

    async def build_response(
        self,
        folder_list: list[dict[str, Any]],
        access_checker: AccessChecker,
    ) -> Response:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._build_response,
            folder_list,
            access_checker,
        )


folder_list_loader = FolderListLoader()


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

    The endpoint handles ACL and optionally also returns folder attributes.
    """

    # The sole purpose of this endpoint is to provide a complete list of
    # folder to the user without blocking other requests. Fast.
    #
    # Project can contain thousands of folders and the result could be up to
    # several megabytes in size, so we need to be careful  not to block other
    # requests while fetching the list and processing the result.
    #
    # Folder list is fetched from redis, where it is stored as JSON in a
    # very similar manner we need to return, but:
    #
    # - for top level keys, it uses snake_case notation as used in the database
    #   instead of camelCase as used in the frontend.
    # - all folders are stored there, so we need to filter out the ones the user
    #   does not have access to. So we cannot avoid parsing the JSON, solving the ACL

    start_time = time.monotonic()
    # _access_list = await folder_access_list(user, project_name, "read")
    # access_list: set[str] | None = (
    #     None if _access_list is None else {r.strip('"') for r in _access_list}
    # )

    access_checker = AccessChecker()
    await access_checker.load(user, project_name, "read")
    access_checker.visualize()

    elapsed_time = time.monotonic() - start_time
    logger.trace(f"Loaded folder access list in {elapsed_time:.3f} seconds")

    start_time = time.monotonic()
    entities = await folder_list_loader.get_folder_list(project_name)
    elapsed_time = time.monotonic() - start_time
    ent_count = len(entities)
    me = f"{ent_count} folders {'with' if attrib else 'without'} attr of {project_name}"
    detail = f"{me} fetched in {elapsed_time:.3f} seconds"
    logger.trace(detail)

    return await folder_list_loader.build_response(entities, access_checker)

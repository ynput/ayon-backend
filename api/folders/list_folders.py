import asyncio
import datetime
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import Query, Response

from ayon_server.access.utils import AccessChecker
from ayon_server.api.dependencies import AllowGuests, CurrentUser, ProjectName
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import OPModel
from ayon_server.utils import camelize, json_dumps, json_loads

from .router import router

# This model is only used for the API documentaion,
# it is not actually used in the code as we stream the json response
# that is generated on the fly.


def _build_response(
    folder_list: list[dict[str, Any]],
    access_checker: AccessChecker,
    attrib_whitelist: set[str] | None = None,
) -> Response:
    def acl_checker(folder: dict[str, Any]) -> bool:
        return access_checker[folder["path"]]

    def attr_parser(folder: dict[str, Any]) -> dict[str, Any]:
        if attrib_whitelist is None:
            return folder

        # folder_list must not be mutated as it could be used
        # by other requests at the same time. therefore, if we
        # pop or filter attributes, we need to do that on a copy

        if attrib_whitelist == set():
            # sligthly faster than copying
            return {k: v for k, v in folder.items() if k not in ("attrib", "ownAttrib")}

        _filtered_attribs = {
            k: v for k, v in folder["attrib"].items() if k in attrib_whitelist
        }
        _filtered_own_attribs = [
            k for k in folder["ownAttrib"] if k in attrib_whitelist
        ]

        _folder = folder.copy()
        _folder["attrib"] = _filtered_attribs
        _folder["ownAttrib"] = _filtered_own_attribs
        return _folder

    return Response(
        json_dumps(
            # {"folders": list(map(attr_parser, filter(acl_checker, folder_list)))},
            {
                "folders": [
                    attr_parser(folder) for folder in folder_list if acl_checker(folder)
                ]
            },
        ),
        media_type="application/json",
    )


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
    has_reviewables: bool = False
    task_names: list[str] | None
    tags: list[str] | None
    status: str
    attrib: dict[str, Any] | None = None
    own_attrib: list[str] | None = None
    created_at: datetime.datetime
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

        entities_data = await Redis.get("project-folders", project_name)
        if entities_data is None:
            folder_list = await rebuild_hierarchy_cache(project_name)
        else:
            folder_list = json_loads(entities_data)

        assert isinstance(folder_list, list)
        return [process_record(record) for record in folder_list]

    async def build_response(
        self,
        folder_list: list[dict[str, Any]],
        access_checker: AccessChecker,
        attrib_whitelist: set[str] | None = None,
    ) -> Response:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            _build_response,
            folder_list,
            access_checker,
            attrib_whitelist,
        )


folder_list_loader = FolderListLoader()


@router.get(
    "",
    response_class=Response,
    responses={200: {"model": FolderListModel}},
    dependencies=[AllowGuests],
)
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

    if user.is_guest:
        # We allow access to this endpoint for guest users
        # but at this moment, it retuns no folders.
        # In the future, we might want to allow access to certain folders
        # for guest users, so we keep the endpoint accessible.
        # This also prevents returning 403 error and flooding the UI with
        # error messages.
        return Response(
            json_dumps(
                {"detail": "Guest users cannot access this endpoint", "folders": []}
            ),
            media_type="application/json",
        )

    start_time = time.monotonic()
    access_checker = AccessChecker()
    await access_checker.load(user, project_name, "read")

    elapsed_time = time.monotonic() - start_time
    logger.trace(f"Loaded folder access list in {elapsed_time:.3f} seconds")

    start_time = time.monotonic()
    entities = await folder_list_loader.get_folder_list(project_name)
    elapsed_time = time.monotonic() - start_time
    ent_count = len(entities)
    me = f"{ent_count} folders {'with' if attrib else 'without'} attr of {project_name}"
    detail = f"{me} fetched in {elapsed_time:.3f} seconds"
    logger.trace(detail)

    attrib_whitelist: set[str] | None = None
    if not attrib:
        attrib_whitelist = set()

    elif not user.is_manager:
        perms = user.permissions(project_name=project_name)
        if perms.attrib_read.enabled:
            attrib_whitelist = set(perms.attrib_read.attributes)
            logger.debug(f"{user} {project_name} attrib whitelist {attrib_whitelist}")

    return await folder_list_loader.build_response(
        entities, access_checker, attrib_whitelist
    )

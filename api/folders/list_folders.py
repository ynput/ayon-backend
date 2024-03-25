import datetime
import time

from ayon_server.access.utils import folder_access_list
from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.lib.redis import Redis
from ayon_server.types import OPModel
from ayon_server.utils import json_loads

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
    task_names: list[str] | None
    status: str
    attrib: dict[str, str]
    own_attrib: list[str]
    updated_at: datetime.datetime


class FolderListModel(OPModel):
    detail: str
    entities: list[FolderListItem]


async def get_entities(project_name: str) -> list[dict[str, str]]:
    entities_data = await Redis.get("project.folders", project_name)
    if entities_data is None:
        return await rebuild_hierarchy_cache(project_name)
    else:
        return json_loads(entities_data)


@router.get("")
async def get_folder_list(
    user: CurrentUser,
    project_name: ProjectName,
) -> FolderListModel:
    """Return all folders in the project. Fast.

    This is a similar endpoint to /hierarchy, but the result
    is a flat list. additionally, this endpoint should be faster
    since it uses a cache. The cache is updated every time a
    folder is created, updated, or deleted.

    The endpoint handles ACL and also returns folder attributes.
    """

    start_time = time.monotonic()
    access_list = await folder_access_list(user, project_name, "read")
    entities = await get_entities(project_name)

    result = {
        "detail": "",
        "entities": [
            entity
            for entity in entities
            if access_list is None or entity["path"] in access_list
        ],
    }

    elapsed_time = time.monotonic() - start_time
    detail = (
        f"{len(result['entities'])} folders "
        f"of {project_name} fetched in {elapsed_time:.2f} seconds"
    )
    result["detail"] = detail

    # we need to do the validation here in order to convert snake_case to camelCase
    return FolderListModel(**result)

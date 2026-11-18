__all__ = ["router"]

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query

from ayon_server.access.task_access import FullAccess, create_task_acl
from ayon_server.access.utils import folder_access_list
from ayon_server.api.dependencies import CurrentUser
from ayon_server.entity_search.search import search
from ayon_server.exceptions import BadRequestException
from ayon_server.types import PROJECT_NAME_REGEX, Field, OPModel

router = APIRouter(prefix="/projects/{project_name}", tags=["Search"])

SearchEntityType = Literal["folder", "task", "product", "version", "comment"]


class SearchFolder(OPModel):
    id: str
    name: str
    label: str | None = None
    folder_type: str
    path: str


class SearchTask(OPModel):
    id: str
    name: str
    label: str | None = None
    task_type: str | None = None


class SearchProduct(OPModel):
    id: str
    name: str
    product_type: str


class SearchVersion(OPModel):
    id: str
    version: int


class SearchComment(OPModel):
    body: str
    author: str | None = None
    created_at: datetime


class SearchResult(OPModel):
    """A matching entity or comment and the entities it belongs to.

    For comments, the target is the deepest entity present
    and `entity_id` is the activity id.
    """

    entity_type: SearchEntityType
    entity_id: str
    rank: float
    folder: SearchFolder
    task: SearchTask | None = None
    product: SearchProduct | None = None
    version: SearchVersion | None = None
    comment: SearchComment | None = None


class SearchResponse(OPModel):
    results: Annotated[list[SearchResult], Field(default_factory=list)]


def _unquote(paths: list[str] | set[str]) -> list[str]:
    """Access lists hold quoted array literal items, the query takes values."""
    return [path.strip('"') for path in paths]


@router.get("/search", response_model_exclude_none=True)
async def search_project(
    # The name ends up in the search_path, so it must be validated here
    user: CurrentUser,
    project_name: Annotated[str, Path(pattern=PROJECT_NAME_REGEX)],
    q: Annotated[str, Query(title="Search text", max_length=200)],
    entity_types: Annotated[list[SearchEntityType] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SearchResponse:
    """Search folders, tasks, products, versions and comments of a project.

    Access is checked like in the GraphQL resolvers: rows are limited
    to the folders the user can read, tasks (and their comments) also
    to the assigned ones when the user cannot see sibling tasks.
    """
    if not q.strip():
        raise BadRequestException("Search text is empty")
    if user.is_guest:
        return SearchResponse(results=[])  # guests see no folders, as in get_folders

    folder_access = await folder_access_list(user, project_name, "read")
    task_access = None
    if (
        not user.is_manager
        and not user.permissions(project_name).advanced.show_sibling_tasks
    ):
        access_groups = user.data.get("accessGroups", {}).get(project_name, [])
        try:
            paths, assigned = await create_task_acl(project_name, access_groups)
        except FullAccess:
            pass
        else:
            task_access = (_unquote(paths), user.name if assigned else None)

    rows = await search(
        project_name,
        q,
        entity_types=list(entity_types or []),
        limit=limit,
        folder_access=None if folder_access is None else _unquote(folder_access),
        task_access=task_access,
    )
    results = []
    for row in rows:
        result = SearchResult(
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            rank=row["rank"],
            folder=SearchFolder(
                id=row["folder_id"],
                name=row["folder_name"],
                label=row["folder_label"],
                folder_type=row["folder_type"],
                path=row["folder_path"],
            ),
        )
        if row["task_id"]:
            result.task = SearchTask(
                id=row["task_id"],
                name=row["task_name"],
                label=row["task_label"],
                task_type=row["task_type"],
            )
        if row["product_id"]:
            result.product = SearchProduct(
                id=row["product_id"],
                name=row["product_name"],
                product_type=row["product_type"],
            )
        if row["version_id"]:
            result.version = SearchVersion(id=row["version_id"], version=row["version"])
        if row["entity_type"] == "comment":
            result.comment = SearchComment(
                body=row["body"], author=row["author"], created_at=row["created_at"]
            )
        results.append(result)
    return SearchResponse(results=results)

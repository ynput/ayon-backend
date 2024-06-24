import time
from typing import TYPE_CHECKING, ForwardRef

from fastapi import APIRouter, Query

from ayon_server.access.utils import folder_access_list
from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils import EntityID, SQLTool

from .solver import HierarchyResolver

router = APIRouter(tags=["Folders"])


#
# [GET] /porjects/{project_name}/hierarchy
#


if not TYPE_CHECKING:
    HierarchyFolderModel = ForwardRef("HierarchyFolderModel")


class HierarchyFolderModel(OPModel):
    id: str = EntityID.field("folder")
    name: str = Field(..., example="Tree", title="Folder name")
    label: str = Field(..., example="Tree", title="Folder label")
    status: str = Field(..., example="Tree", title="Folder status")
    folderType: str | None = Field(example="AssetBuild", title="Folder type")
    hasTasks: bool
    taskNames: list[str] = Field(example=["Modeling", "Rigging"], title="Task names")
    parents: list[str]
    parentId: str | None = Field(None, title="Parent folder id")
    children: list[HierarchyFolderModel] = Field(
        default_factory=list,
        title="List of children",
    )


HierarchyFolderModel.update_forward_refs()


class HierarchyResponseModel(OPModel):
    detail: str
    projectName: str
    hierarchy: list[HierarchyFolderModel]


@router.get("/projects/{project_name}/hierarchy")
async def get_folder_hierarchy(
    project_name: ProjectName,
    user: CurrentUser,
    search: str = Query(
        "",
        title="Search query",
        description="Full-text search query used to limit the result",
        example="forest",
    ),
    types: str = Query(
        "",
        title="Type filter",
        description="Comma separated list of folder_types to show",
        example="AssetBuild,Shot,Sequence",
    ),
) -> HierarchyResponseModel:
    """Return a folder hierarchy of a project."""

    start_time = time.time()

    type_list = [t.strip() for t in types.split(",") if t.strip()]

    hierarchy = HierarchyResolver()

    conds = []
    if type_list:
        conds.append(f"folder_type IN {SQLTool.array(type_list)}")

    access_list = await folder_access_list(user, project_name, "read")

    if access_list is not None:
        conds.append(f"path like ANY ('{{ {','.join(access_list)} }}')")

    # TODO: eventually solve products too. ATM it clashes with the
    # task names list (group by hell), which is more important.

    plain_result = []
    query = f"""
        SELECT
            folders.id,
            folders.parent_id,
            folders.folder_type,
            folders.name,
            folders.label,
            folders.status,
            hierarchy.path as path,
            -- COUNT (products.id) AS product_count,
            COUNT (tasks.id) AS task_count,
            array_agg(tasks.name) AS task_names
        FROM
            project_{project_name}.folders AS folders
        INNER JOIN
            project_{project_name}.hierarchy AS hierarchy
        ON
            folders.id = hierarchy.id
        -- LEFT JOIN
        --     project_{project_name}.products AS products
        -- ON
        --     products.folder_id = folders.id
        LEFT JOIN
            project_{project_name}.tasks AS tasks
        ON
            tasks.folder_id = folders.id
        {SQLTool.conditions(conds)}
        GROUP BY folders.id, hierarchy.path
        ORDER BY folders.name ASC
    """
    async for row in Postgres.iterate(query):
        d = {
            "id": row["id"],
            "parentId": row["parent_id"],
            "name": row["name"],
            "label": row["label"] or row["name"],
            "status": row["status"],
            "folderType": row["folder_type"],
            "parents": row["path"].split("/")[:-1],
            "hasTasks": bool(row["task_count"]),
            "taskNames": row["task_names"] if row["task_count"] else [],
        }
        if types:
            plain_result.append(d)
        else:
            hierarchy.append(d)

    if type_list:
        hresult = plain_result
    else:
        hierarchy.commit()
        hresult = hierarchy()

    res = HierarchyResponseModel.construct(
        detail="Working",
        projectName=project_name,
        hierarchy=hresult,  # type: ignore
    )
    elapsed = round(time.time() - start_time, 4)
    detail = f"Hierarchy loaded in {elapsed}s"
    res.detail = detail
    return res

import time

from typing import Optional, ForwardRef
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, Response

from openpype.utils import EntityID, SQLTool
from openpype.entities import UserEntity
from openpype.exceptions import ForbiddenException
from openpype.hierarchy import HierarchyResolver
from openpype.access.utils import folder_access_conds
from openpype.lib.postgres import Postgres
from openpype.api import (
    ResponseFactory,
    APIException,
    dep_current_user,
    dep_project_name
)


#
# Router
#


router = APIRouter(
    tags=["Folders"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403)
    }
)


#
# [GET] /porjects/{project_name}/hierarchy
#


HierarchyFolderModel = ForwardRef('HierarchyFolderModel')


class HierarchyFolderModel(BaseModel):
    id: str = EntityID.field("folder")
    name: str = Field(..., example="Tree", title="Folder name")
    type: str | None = Field(example="AssetBuild", title="Folder type")
    subsetCount: int
    parents: list[str]
    children: list[HierarchyFolderModel] = Field(
        default_factory=list,
        title="List of children"
    )


HierarchyFolderModel.update_forward_refs()


class HierarchyResponseModel(BaseModel):
    detail: str
    projectName: str
    hierarchy: list[HierarchyFolderModel]


@router.get(
    "/projects/{project_name}/hierarchy",
    response_model=HierarchyResponseModel
)
async def get_folder_hierarchy(
    project_name: str = Depends(dep_project_name),
    user: UserEntity = Depends(dep_current_user),
    search: Optional[str] = Query(
        "",
        title="Search query",
        description="Full-text search query used to limit the result",
        example="forest"
    ),
    types: Optional[str] = Query(
        "",
        title="Type filter",
        description="Comma separated list of folder_types to show",
        example="AssetBuild,Shot,Sequence"
    )
):
    """Return a hierarchy of a project."""

    start_time = time.time()

    type_list = [
        t.strip() for t in types.split(",") if t.strip()
    ]

    hierarchy = HierarchyResolver()

    conds = []
    if type_list:
        conds.append(
            f"folder_type IN {SQLTool.array(type_list)}"
        )

    try:
        access_conds = await folder_access_conds(user, project_name, "read")
    except ForbiddenException:
        raise APIException(403)

    if access_conds:
        conds.append(access_conds)

    plain_result = []
    query = f"""
        SELECT
            folders.id,
            folders.parent_id,
            folders.folder_type,
            folders.name,
            hierarchy.path as path,
            COUNT (subsets.id) AS subset_count
        FROM
            project_{project_name}.folders AS folders
        INNER JOIN
            project_{project_name}.hierarchy AS hierarchy
        ON
            folders.id = hierarchy.id
        LEFT JOIN
            project_{project_name}.subsets AS subsets
        ON
            subsets.folder_id = folders.id
        {SQLTool.conditions(conds)}
        GROUP BY folders.id, hierarchy.path
        ORDER BY folders.name ASC
    """
    async for row in Postgres.iterate(query):
        d = {
            "id": EntityID.parse(row["id"]),
            "parentId": EntityID.parse(row["parent_id"], allow_nulls=True),
            "name": row["name"],
            "type": row["folder_type"],
            "parents": row["path"].split("/")[:-1],
            "subsetCount": row["subset_count"]
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

    elapsed = round(time.time() - start_time, 4)

    return HierarchyResponseModel.construct(
        detail=f"Hierarchy loaded in {elapsed}s",
        projectName=project_name,
        hierarchy=hresult
    )


#
# Change hierarchy
# TODO: Use a list of changes to allow modification of multiple folders at once
#


class HierarchyChangeModel(BaseModel):
    id: Optional[str] = EntityID.field("folder")
    children: list[str] = Field(default_factory=list, example=[])


@router.post(
    "/projects/{project_name}/hierarchy",
    status_code=204,
    response_class=Response
)
async def change_hierarchy(
    project_name: str = Depends(dep_project_name),
    user: UserEntity = Depends(dep_current_user),
    body: HierarchyChangeModel = ...
):
    """
    Change the hierarchy of a project.

    Set a folder as a parent of another folder(s)
    """

    # TODO: Error handling

    children = [ch for ch in body.children if ch != body.id]

    async with Postgres.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                f"""
                UPDATE project_{project_name}.folders SET
                parent_id = $1
                WHERE id IN {SQLTool.id_array(children)}
                """,
                body.id
            )

            await conn.execute(
                f"""
                REFRESH MATERIALIZED VIEW CONCURRENTLY
                project_{project_name}.hierarchy
                """)

    return Response(status_code=204)

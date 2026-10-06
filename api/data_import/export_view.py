"""Export folders and tasks as shown in a project table (or a selection of it).

Rows are fetched through the GraphQL resolvers the project overview uses, so
filters, folder access and attribute permissions match what the user sees, and
attributes include inherited values. The CSV uses the hierarchy import format,
so it can be edited and imported back.
"""

import csv
import io
import json
from datetime import date
from typing import Any, Literal

from fastapi import Query, Request
from fastapi.responses import Response

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import AyonException, BadRequestException
from ayon_server.graphql import graphql_get_context
from ayon_server.graphql import router as graphql_router
from ayon_server.helpers.project_list import normalize_project_name
from ayon_server.types import PROJECT_NAME_REGEX, Field, OPModel

from .models import HIERARCHY_UNIFIED_COLUMN, FolderTaskExportImportModel
from .router import router

PAGE_SIZE = 2000
LEADING_COLUMNS = ["entity_type", "path"]

PROJECT_QUERY = """
query ExportProject($projectName: String!) { project(name: $projectName) { name } }
"""

FOLDERS_QUERY = """
query ExportFolders(
  $projectName: String!, $ids: [String!], $first: Int!, $after: String
) {
  project(name: $projectName) {
    folders(ids: $ids, first: $first, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { node {
        id name label folderType parentId path active status tags allAttrib
      } }
    }
  }
}
"""

TASKS_QUERY = """
query ExportTasks(
  $projectName: String!
  $ids: [String!]
  $folderIds: [String!]
  $includeFolderChildren: Boolean!
  $filter: String
  $folderFilter: String
  $search: String
  $first: Int!
  $after: String
) {
  project(name: $projectName) {
    tasks(
      ids: $ids
      folderIds: $folderIds
      includeFolderChildren: $includeFolderChildren
      filter: $filter
      folderFilter: $folderFilter
      search: $search
      first: $first
      after: $after
    ) {
      pageInfo { hasNextPage endCursor }
      edges { node {
        id name label taskType folderId active status tags assignees allAttrib
        folder { path }
      } }
    }
  }
}
"""


class ExportTasksQuery(OPModel):
    ids: list[str] | None = Field(None, description="Only tasks with these ids")
    folder_ids: list[str] | None = Field(
        None, description="Only tasks in these folders"
    )
    include_folder_children: bool = Field(
        True, description="Include tasks in subfolders of folder_ids"
    )
    filter: str | None = Field(None, description="Task QueryFilter (JSON)")
    folder_filter: str | None = Field(
        None, description="QueryFilter (JSON) the task's folder has to match"
    )
    search: str | None = Field(None, description="Fuzzy text search")


class ExportViewRequest(OPModel):
    columns: list[str] = Field(
        default_factory=list,
        description=(
            "Field keys to export after entity_type and path, in order. "
            "See /csv/export/hierarchy/fields"
        ),
        example=["folder_or_task_type", "status", "assignees", "attrib.priority"],
    )
    folder_ids: list[str] | None = Field(None, description="Folders to export as rows")
    tasks: ExportTasksQuery | None = Field(None, description="Tasks to export as rows")
    delimiter: Literal[",", ";", "\t"] = Field(",", description="Column delimiter")


@router.post("/export/hierarchy/view")
async def export_hierarchy_view(
    request: Request,
    user: CurrentUser,
    payload: ExportViewRequest,
    project_name: str = Query(..., regex=PROJECT_NAME_REGEX),
) -> Response:
    """Export folders and tasks of a project table as CSV.

    Folder rows are given by id, task rows by the same arguments the GraphQL
    tasks query takes. Users only get the entities and attributes they can read.
    """
    project_name = await normalize_project_name(project_name)
    context = await graphql_get_context(request, user)
    # same project access check as the table's own queries
    await _execute(context, PROJECT_QUERY, {"projectName": project_name})

    fields = await FolderTaskExportImportModel.fields(project_name=project_name)
    labels = {field.key: field.label or field.key for field in fields}
    columns = LEADING_COLUMNS + [
        key for key in dict.fromkeys(payload.columns) if key not in LEADING_COLUMNS
    ]
    if unknown := [key for key in columns if key not in labels]:
        raise BadRequestException(f"Unknown columns: {', '.join(unknown)}")

    rows: list[dict[str, Any]] = []
    variables: dict[str, Any]

    if payload.folder_ids:
        variables = {"projectName": project_name, "ids": payload.folder_ids}
        for node in await _fetch(context, FOLDERS_QUERY, "folders", variables):
            rows.append(_folder_row(node))

    if payload.tasks and payload.tasks.ids != []:
        variables = {
            "projectName": project_name,
            "ids": payload.tasks.ids,
            "folderIds": payload.tasks.folder_ids,
            "includeFolderChildren": payload.tasks.include_folder_children,
            "filter": payload.tasks.filter,
            "folderFilter": payload.tasks.folder_filter,
            "search": payload.tasks.search,
        }
        for node in await _fetch(context, TASKS_QUERY, "tasks", variables):
            rows.append(_task_row(node))

    rows.sort(key=_tree_order)

    buffer = io.StringIO()
    buffer.write("﻿")  # BOM, without it Excel reads the file as ANSI
    writer = csv.writer(buffer, delimiter=payload.delimiter)
    writer.writerow(_unique_labels([labels[key] for key in columns]))
    for row in rows:
        writer.writerow([_format(row.get(key)) for key in columns])

    extension = "tsv" if payload.delimiter == "\t" else "csv"
    filename = f"{project_name}_export_{date.today().isoformat()}.{extension}"
    return Response(
        content=buffer.getvalue(),
        media_type=f"text/{extension}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _execute(
    context: dict[str, Any], query: str, variables: dict[str, Any]
) -> dict[str, Any]:
    result = await graphql_router.schema.execute(
        query, variable_values=variables, context_value=context
    )
    if result.errors:
        error = result.errors[0]
        if isinstance(error.original_error, AyonException):
            raise error.original_error
        raise BadRequestException(error.message)
    assert result.data is not None
    return result.data


async def _fetch(
    context: dict[str, Any], query: str, connection: str, variables: dict[str, Any]
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    after = None
    while True:
        data = await _execute(
            context, query, {**variables, "first": PAGE_SIZE, "after": after}
        )
        page = data["project"][connection]
        nodes.extend(edge["node"] for edge in page["edges"])
        if not page["pageInfo"]["hasNextPage"]:
            return nodes
        after = page["pageInfo"]["endCursor"]


def _attrib(node: dict[str, Any]) -> dict[str, Any]:
    return {f"attrib.{k}": v for k, v in json.loads(node["allAttrib"]).items()}


def _folder_row(node: dict[str, Any]) -> dict[str, Any]:
    return {
        **_attrib(node),
        "entity_type": "folder",
        "path": (node["path"] or "").strip("/"),
        "id": node["id"],
        "name": node["name"],
        "label": node["label"],
        "folder_type": node["folderType"],
        HIERARCHY_UNIFIED_COLUMN: node["folderType"],
        "parent_id": node["parentId"],
        "active": node["active"],
        "status": node["status"],
        "tags": node["tags"],
    }


def _task_row(node: dict[str, Any]) -> dict[str, Any]:
    folder_path = (node["folder"]["path"] or "").strip("/")
    return {
        **_attrib(node),
        "entity_type": "task",
        "path": f"{folder_path}/{node['name']}",
        "id": node["id"],
        "name": node["name"],
        "label": node["label"],
        "task_type": node["taskType"],
        HIERARCHY_UNIFIED_COLUMN: node["taskType"],
        "folder_id": node["folderId"],
        "active": node["active"],
        "status": node["status"],
        "tags": node["tags"],
        "assignees": node["assignees"],
    }


def _tree_order(row: dict[str, Any]) -> list[tuple[int, str]]:
    # depth first, and a folder's tasks before its subfolders
    *parents, name = row["path"].split("/")
    return [(1, part) for part in parents] + [
        (0 if row["entity_type"] == "task" else 1, name)
    ]


def _format(value: Any) -> str:
    """Write values the way the importer reads them back."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(_format(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)


def _unique_labels(labels: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for label in labels:
        seen[label] = seen.get(label, 0) + 1
        result.append(label if seen[label] == 1 else f"{label} ({seen[label]})")
    return result

"""Export rows of a project table (or a selection of it) as CSV or XLSX.

Rows are fetched through the GraphQL resolvers the project tables use, so
filters, folder access and attribute permissions match what the user sees, and
attributes include inherited values. A request can combine folders, tasks,
products, versions and the items of an entity list.

With field names as headers, raw values and the entity_type and path columns,
a folder and task export is in the hierarchy import format and can be imported
back. Labels make a file for reading: column names as in the table, enum labels,
full names of users and readable dates.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from fastapi import Query, Request
from fastapi.responses import Response

from ayon_server.api.dependencies import CurrentUser
from ayon_server.entities import ProductEntity, VersionEntity
from ayon_server.exceptions import AyonException, BadRequestException
from ayon_server.graphql import graphql_get_context
from ayon_server.graphql import router as graphql_router
from ayon_server.helpers.project_list import normalize_project_name
from ayon_server.types import PROJECT_NAME_REGEX, Field, OPModel

from .models import (
    HIERARCHY_UNIFIED_COLUMN,
    EntityExportImport,
    FolderTaskExportImportModel,
)
from .router import router
from .table_file import XLSX_MEDIA_TYPE, Cell, write_csv, write_xlsx

PAGE_SIZE = 2000

FOLDER_FRAGMENT = """
fragment ExportFolder on FolderNode {
  id name label folderType parentId path active status tags allAttrib
  createdAt updatedAt
}
"""

TASK_FRAGMENT = """
fragment ExportTask on TaskNode {
  id name label taskType folderId active status tags assignees allAttrib
  createdAt updatedAt
  folder { name label path }
}
"""

# needs $featuredVersionOrder in the query
PRODUCT_FRAGMENT = """
fragment ExportProduct on ProductNode {
  id name productType productBaseType path active status tags allAttrib
  createdAt updatedAt
  folder { name label }
  featuredVersion(order: $featuredVersionOrder) { name author }
}
"""

VERSION_FRAGMENT = """
fragment ExportVersion on VersionNode {
  id name author path active status tags allAttrib createdAt updatedAt
  product { name productType productBaseType folder { name label } }
  task { name label taskType }
}
"""

PROJECT_QUERY = """
query ExportProject($projectName: String!) { project(name: $projectName) { name } }
"""

USERS_QUERY = """
query ExportUsers($projectName: String!, $names: [String!]!, $first: Int!) {
  users(projectName: $projectName, names: $names, first: $first) {
    edges { node { name attrib { fullName } } }
  }
}
"""

FOLDERS_QUERY = (
    """
query ExportFolders(
  $projectName: String!, $ids: [String!], $first: Int!, $after: String
) {
  project(name: $projectName) {
    folders(ids: $ids, first: $first, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { node { ...ExportFolder } }
    }
  }
}
"""
    + FOLDER_FRAGMENT
)

TASKS_QUERY = (
    """
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
      edges { node { ...ExportTask } }
    }
  }
}
"""
    + TASK_FRAGMENT
)

PRODUCTS_QUERY = (
    """
query ExportProducts(
  $projectName: String!
  $ids: [String!]
  $folderIds: [String!]
  $includeFolderChildren: Boolean!
  $filter: String
  $folderFilter: String
  $versionFilter: String
  $taskFilter: String
  $sortBy: [String!]
  $featuredVersionOrder: [String!]
  $first: Int!
  $after: String
) {
  project(name: $projectName) {
    products(
      ids: $ids
      folderIds: $folderIds
      includeFolderChildren: $includeFolderChildren
      filter: $filter
      folderFilter: $folderFilter
      versionFilter: $versionFilter
      taskFilter: $taskFilter
      sortBy: $sortBy
      first: $first
      after: $after
    ) {
      pageInfo { hasNextPage endCursor }
      edges { node { ...ExportProduct } }
    }
  }
}
"""
    + PRODUCT_FRAGMENT
)

VERSIONS_QUERY = (
    """
query ExportVersions(
  $projectName: String!
  $ids: [String!]
  $productIds: [String!]
  $folderIds: [String!]
  $includeFolderChildren: Boolean!
  $filter: String
  $folderFilter: String
  $productFilter: String
  $taskFilter: String
  $featuredOnly: [String!]
  $latestPerFolder: Boolean!
  $hasReviewables: Boolean
  $sortBy: [String!]
  $first: Int!
  $after: String
) {
  project(name: $projectName) {
    versions(
      ids: $ids
      productIds: $productIds
      folderIds: $folderIds
      includeFolderChildren: $includeFolderChildren
      filter: $filter
      folderFilter: $folderFilter
      productFilter: $productFilter
      taskFilter: $taskFilter
      featuredOnly: $featuredOnly
      latestPerFolder: $latestPerFolder
      hasReviewables: $hasReviewables
      sortBy: $sortBy
      first: $first
      after: $after
    ) {
      pageInfo { hasNextPage endCursor }
      edges { node { ...ExportVersion } }
    }
  }
}
"""
    + VERSION_FRAGMENT
)

LIST_QUERY = """
query ExportList($projectName: String!, $id: String!) {
  project(name: $projectName) { entityList(id: $id) { attributes } }
}
"""

LIST_ITEMS_QUERY = (
    """
query ExportListItems(
  $projectName: String!
  $id: String!
  $filter: String
  $search: String
  $sortBy: [String!]
  $featuredVersionOrder: [String!]
  $first: Int!
  $after: String
) {
  project(name: $projectName) {
    entityList(id: $id) {
      items(
        filter: $filter
        search: $search
        sortBy: $sortBy
        accessibleOnly: true
        first: $first
        after: $after
      ) {
        pageInfo { hasNextPage endCursor }
        edges {
          id allAttrib
          node {
            ... on FolderNode { ...ExportFolder }
            ... on TaskNode { ...ExportTask }
            ... on ProductNode { ...ExportProduct }
            ... on VersionNode { ...ExportVersion }
          }
        }
      }
    }
  }
}
"""
    + FOLDER_FRAGMENT
    + TASK_FRAGMENT
    + PRODUCT_FRAGMENT
    + VERSION_FRAGMENT
)

ENTITY_TYPE_LABELS = {
    "folder": "Folder",
    "task": "Task",
    "product": "Product",
    "version": "Version",
}


@dataclass
class ExportColumn:
    key: str
    label: str
    value_type: str = "string"
    enum_labels: dict[str, str] = field(default_factory=dict)
    users: bool = False  # values are user names


# Columns that are not fields of the exported entity. Read only, the importer
# ignores them.
EXTRA_COLUMNS = [
    ExportColumn("folder", "Folder"),
    ExportColumn("task", "Task"),
    ExportColumn("product", "Product"),
    ExportColumn("version", "Version"),
    ExportColumn("author", "Author", users=True),
    ExportColumn("product_type", "Product type"),
    ExportColumn("product_base_type", "Product base type"),
    ExportColumn("created_at", "Created", "datetime"),
    ExportColumn("updated_at", "Updated", "datetime"),
]

# shown instead of the value with label values
DISPLAY_KEYS = {"name": "label", "folder": "folder_label", "task": "task_label"}


class _ProductFields(EntityExportImport):
    _entity_model = ProductEntity


class _VersionFields(EntityExportImport):
    _entity_model = VersionEntity


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


class ExportProductsQuery(OPModel):
    ids: list[str] | None = Field(None, description="Only products with these ids")
    folder_ids: list[str] | None = Field(
        None, description="Only products in these folders"
    )
    include_folder_children: bool = Field(
        True, description="Include products in subfolders of folder_ids"
    )
    filter: str | None = Field(None, description="Product QueryFilter (JSON)")
    folder_filter: str | None = Field(None, description="Folder QueryFilter (JSON)")
    version_filter: str | None = Field(None, description="Version QueryFilter (JSON)")
    task_filter: str | None = Field(None, description="Task QueryFilter (JSON)")
    sort_by: list[str] | None = Field(
        None, description="Row order, as the GraphQL sortBy argument"
    )
    featured_version_order: list[str] | None = Field(
        None, description="Which version fills the version and author columns"
    )


class ExportVersionsQuery(OPModel):
    ids: list[str] | None = Field(None, description="Only versions with these ids")
    product_ids: list[str] | None = Field(
        None,
        description=(
            "Only versions of these products. "
            "Without ids, versions exported with products are those of the products"
        ),
    )
    folder_ids: list[str] | None = Field(
        None, description="Only versions in these folders"
    )
    include_folder_children: bool = Field(
        True, description="Include versions in subfolders of folder_ids"
    )
    filter: str | None = Field(None, description="Version QueryFilter (JSON)")
    folder_filter: str | None = Field(None, description="Folder QueryFilter (JSON)")
    product_filter: str | None = Field(None, description="Product QueryFilter (JSON)")
    task_filter: str | None = Field(None, description="Task QueryFilter (JSON)")
    featured_only: list[str] | None = Field(
        None, description="One version per product: 'hero', 'latestDone', 'latest'"
    )
    latest_per_folder: bool = Field(False, description="Latest version per folder")
    has_reviewables: bool | None = Field(
        None, description="Only versions with (or without) reviewables"
    )
    sort_by: list[str] | None = Field(
        None, description="Row order, as the GraphQL sortBy argument"
    )


class ExportListQuery(OPModel):
    id: str = Field(..., description="Entity list id")
    item_ids: list[str] | None = Field(None, description="Only these list items")
    filter: str | None = Field(None, description="List item QueryFilter (JSON)")
    search: str | None = Field(None, description="Fuzzy text search")
    sort_by: list[str] | None = Field(
        None, description="Row order, as the GraphQL sortBy argument"
    )


class ExportTableRequest(OPModel):
    columns: list[str] = Field(
        default_factory=list,
        description=(
            "Column keys in order: entity fields (`status`, `attrib.priority`...), "
            "`entity_type`, `path`, `folder`, `task`, `product`, `version`, "
            "`author`, `created_at` and `updated_at`"
        ),
        example=["entity_type", "path", "status", "assignees", "attrib.priority"],
    )
    column_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Column names to use instead of the field labels",
        example={"name": "Folder / Task"},
    )
    folder_ids: list[str] | None = Field(None, description="Folders to export as rows")
    tasks: ExportTasksQuery | None = Field(None, description="Tasks to export as rows")
    products: ExportProductsQuery | None = Field(
        None, description="Products to export as rows"
    )
    versions: ExportVersionsQuery | None = Field(
        None, description="Versions to export as rows"
    )
    entity_list: ExportListQuery | None = Field(
        None, description="List items to export as rows"
    )
    format: Literal["csv", "xlsx"] = Field("csv", description="File format")
    delimiter: Literal[",", ";", "\t"] = Field(",", description="CSV delimiter")
    header: Literal["label", "key"] = Field(
        "label", description="Column names: labels or field names (keys)"
    )
    values: Literal["value", "label"] = Field(
        "value",
        description=(
            "Raw values, or labels: enum labels, full names of users, "
            "readable dates and names replaced by labels"
        ),
    )


@router.post("/table/export")
async def export_table(
    request: Request,
    user: CurrentUser,
    payload: ExportTableRequest,
    project_name: str = Query(..., regex=PROJECT_NAME_REGEX),
) -> Response:
    """Export rows of a project table as CSV or XLSX.

    Folder rows are given by id; tasks, products, versions and list items by
    the arguments of their GraphQL queries. Users only get the entities and
    attributes they can read.

    Folders and tasks are ordered depth first, products with their versions by
    path. Other rows keep the order of the query.
    """
    project_name = await normalize_project_name(project_name)
    context = await graphql_get_context(request, user)
    # same project access check as the table's own queries
    await _execute(context, PROJECT_QUERY, {"projectName": project_name})

    variables: dict[str, Any] = {"projectName": project_name}
    available = await _available_columns(project_name)
    if payload.entity_list:
        variables["id"] = payload.entity_list.id
        data = await _execute(context, LIST_QUERY, variables)
        for column in _list_attribute_columns(data["project"]["entityList"]):
            available.setdefault(column.key, column)

    keys = list(dict.fromkeys(payload.columns))
    unknown = [k for k in keys if k not in available and not k.startswith("attrib.")]
    if unknown:
        raise BadRequestException(f"Unknown columns: {', '.join(unknown)}")
    columns = [available.get(key) or ExportColumn(key, key[7:]) for key in keys]

    rows = await _fetch_rows(context, project_name, payload)

    labels = payload.values == "label"
    users = (
        await _user_full_names(context, project_name, rows, columns) if labels else {}
    )

    if payload.header == "key":
        header = [column.key for column in columns]
    else:
        header = _unique([payload.column_labels.get(c.key, c.label) for c in columns])
    cells = [[_cell(row, column, labels, users) for column in columns] for row in rows]

    stem = f"{project_name}_export_{date.today().isoformat()}"
    if payload.format == "xlsx":
        content = write_xlsx(header, cells, project_name)
        filename, media_type = f"{stem}.xlsx", XLSX_MEDIA_TYPE
    else:
        text_rows = [[_text(cell, labels) for cell in row] for row in cells]
        content = write_csv(header, text_rows, payload.delimiter)
        extension = "tsv" if payload.delimiter == "\t" else "csv"
        filename = f"{stem}.{extension}"
        media_type = f"text/{extension}; charset=utf-8"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _fetch_rows(
    context: dict[str, Any], project_name: str, payload: ExportTableRequest
) -> list[dict[str, Any]]:
    base: dict[str, Any] = {"projectName": project_name}
    tree_rows: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    if payload.folder_ids:
        variables = {**base, "ids": payload.folder_ids}
        for node in await _fetch(context, FOLDERS_QUERY, ["folders"], variables):
            tree_rows.append(_folder_row(node))

    if (tasks := payload.tasks) and tasks.ids != []:
        variables = {
            **base,
            "ids": tasks.ids,
            "folderIds": tasks.folder_ids,
            "includeFolderChildren": tasks.include_folder_children,
            "filter": tasks.filter,
            "folderFilter": tasks.folder_filter,
            "search": tasks.search,
        }
        for node in await _fetch(context, TASKS_QUERY, ["tasks"], variables):
            tree_rows.append(_task_row(node))

    product_rows: list[dict[str, Any]] = []
    if (products := payload.products) and products.ids != []:
        variables = {
            **base,
            "ids": products.ids,
            "folderIds": products.folder_ids,
            "includeFolderChildren": products.include_folder_children,
            "filter": products.filter,
            "folderFilter": products.folder_filter,
            "versionFilter": products.version_filter,
            "taskFilter": products.task_filter,
            "sortBy": products.sort_by,
            "featuredVersionOrder": products.featured_version_order,
        }
        for node in await _fetch(context, PRODUCTS_QUERY, ["products"], variables):
            product_rows.append(_product_row(node))

    version_rows: list[dict[str, Any]] = []
    versions = payload.versions
    product_ids = versions.product_ids if versions else None
    if versions and payload.products and versions.ids is None and product_ids is None:
        product_ids = [row["id"] for row in product_rows]
    if versions and versions.ids != [] and product_ids != []:
        variables = {
            **base,
            "ids": versions.ids,
            "productIds": product_ids,
            "folderIds": versions.folder_ids,
            "includeFolderChildren": versions.include_folder_children,
            "filter": versions.filter,
            "folderFilter": versions.folder_filter,
            "productFilter": versions.product_filter,
            "taskFilter": versions.task_filter,
            "featuredOnly": versions.featured_only,
            "latestPerFolder": versions.latest_per_folder,
            "hasReviewables": versions.has_reviewables,
            "sortBy": versions.sort_by,
        }
        for node in await _fetch(context, VERSIONS_QUERY, ["versions"], variables):
            version_rows.append(_version_row(node))

    # products with their versions, as in the products table
    if product_rows and version_rows:
        tree_rows += product_rows + version_rows
    else:
        rows += product_rows + version_rows

    if (entity_list := payload.entity_list) and entity_list.item_ids != []:
        item_ids = set(entity_list.item_ids or [])
        variables = {
            **base,
            "id": entity_list.id,
            "filter": entity_list.filter,
            "search": entity_list.search,
            "sortBy": entity_list.sort_by,
            "featuredVersionOrder": None,
        }
        path = ["entityList", "items"]
        for edge in await _fetch(context, LIST_ITEMS_QUERY, path, variables, True):
            if edge["node"] is None or (item_ids and edge["id"] not in item_ids):
                continue
            row = _entity_row(edge["node"])
            # list item attributes win over the entity's
            row.update(_attrib(edge))
            rows.append(row)

    tree_rows.sort(key=_tree_order)
    return tree_rows + rows


async def _available_columns(project_name: str) -> dict[str, ExportColumn]:
    columns: dict[str, ExportColumn] = {}
    for model in (FolderTaskExportImportModel, _ProductFields, _VersionFields):
        for f in await model.fields(project_name=project_name):
            if f.key in columns:
                continue
            columns[f.key] = ExportColumn(
                key=f.key,
                label=f.label or f.key,
                value_type=f.value_type or "string",
                enum_labels={
                    str(item.value): item.label
                    for item in f.enum_items or []
                    if item.label
                },
                users=f.key == "assignees",
            )
    columns["entity_type"].enum_labels = ENTITY_TYPE_LABELS
    columns[HIERARCHY_UNIFIED_COLUMN].label = "Type"
    for column in EXTRA_COLUMNS:
        columns[column.key] = column
    return columns


def _list_attribute_columns(entity_list: dict[str, Any]) -> list[ExportColumn]:
    columns = []
    for attribute in json.loads(entity_list["attributes"] or "[]"):
        data = attribute.get("data") or {}
        columns.append(
            ExportColumn(
                key=f"attrib.{attribute['name']}",
                label=data.get("title") or attribute["name"],
                value_type=data.get("type") or "string",
                enum_labels={
                    str(item["value"]): item["label"]
                    for item in data.get("enum") or []
                    if item.get("label")
                },
            )
        )
    return columns


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
    context: dict[str, Any],
    query: str,
    path: list[str],
    variables: dict[str, Any],
    edges: bool = False,
) -> list[dict[str, Any]]:
    """All nodes (or edges) of a paginated connection under `project`."""
    result: list[dict[str, Any]] = []
    after = None
    while True:
        data = await _execute(
            context, query, {**variables, "first": PAGE_SIZE, "after": after}
        )
        page = data["project"]
        for key in path:
            page = page[key]
        result.extend(edge if edges else edge["node"] for edge in page["edges"])
        if not page["pageInfo"]["hasNextPage"]:
            return result
        after = page["pageInfo"]["endCursor"]


async def _user_full_names(
    context: dict[str, Any],
    project_name: str,
    rows: list[dict[str, Any]],
    columns: list[ExportColumn],
) -> dict[str, str]:
    names: set[str] = set()
    for column in columns:
        if column.users:
            for row in rows:
                value = row.get(column.key)
                if isinstance(value, list):
                    names.update(value)
                elif value:
                    names.add(value)
    if not names:
        return {}
    variables = {"projectName": project_name, "names": sorted(names), "first": 1000}
    try:
        data = await _execute(context, USERS_QUERY, variables)
    except AyonException:
        return {}  # fall back to user names
    return {
        edge["node"]["name"]: edge["node"]["attrib"]["fullName"]
        for edge in data["users"]["edges"]
        if edge["node"]["attrib"]["fullName"]
    }


def _attrib(node: dict[str, Any]) -> dict[str, Any]:
    return {f"attrib.{k}": v for k, v in json.loads(node["allAttrib"]).items()}


def _common(node: dict[str, Any], entity_type: str) -> dict[str, Any]:
    return {
        **_attrib(node),
        "entity_type": entity_type,
        "id": node["id"],
        "name": node["name"],
        "active": node["active"],
        "status": node["status"],
        "tags": node["tags"],
        "created_at": node["createdAt"],
        "updated_at": node["updatedAt"],
    }


def _entity_row(node: dict[str, Any]) -> dict[str, Any]:
    if "folderType" in node:
        return _folder_row(node)
    if "taskType" in node:
        return _task_row(node)
    if "productType" in node:
        return _product_row(node)
    return _version_row(node)


def _folder_row(node: dict[str, Any]) -> dict[str, Any]:
    return {
        **_common(node, "folder"),
        "path": (node["path"] or "").strip("/"),
        "label": node["label"],
        "folder_type": node["folderType"],
        HIERARCHY_UNIFIED_COLUMN: node["folderType"],
        "parent_id": node["parentId"],
    }


def _task_row(node: dict[str, Any]) -> dict[str, Any]:
    folder = node["folder"]
    return {
        **_common(node, "task"),
        "path": f"{(folder['path'] or '').strip('/')}/{node['name']}",
        "label": node["label"],
        "task_type": node["taskType"],
        HIERARCHY_UNIFIED_COLUMN: node["taskType"],
        "folder_id": node["folderId"],
        "folder": folder["name"],
        "folder_label": folder["label"],
        "assignees": node["assignees"],
    }


def _product_row(node: dict[str, Any]) -> dict[str, Any]:
    folder = node["folder"]
    featured = node["featuredVersion"] or {}
    return {
        **_common(node, "product"),
        "path": (node["path"] or "").strip("/"),
        "product_type": node["productType"],
        "product_base_type": node["productBaseType"],
        "folder": folder["name"],
        "folder_label": folder["label"],
        "version": featured.get("name"),
        "author": featured.get("author"),
    }


def _version_row(node: dict[str, Any]) -> dict[str, Any]:
    product = node["product"]
    task = node["task"] or {}
    return {
        **_common(node, "version"),
        "path": (node["path"] or "").strip("/"),
        # shown as the name with label values, "v001" alone says little
        "label": f"{product['name']} {node['name']}",
        "version": node["name"],
        "author": node["author"],
        "product": product["name"],
        "product_type": product["productType"],
        "product_base_type": product["productBaseType"],
        "folder": product["folder"]["name"],
        "folder_label": product["folder"]["label"],
        "task": task.get("name"),
        "task_label": task.get("label"),
        "task_type": task.get("taskType"),
    }


def _tree_order(row: dict[str, Any]) -> list[tuple[int, str]]:
    # depth first, and a folder's tasks before its subfolders
    *parents, name = row["path"].split("/")
    return [(1, part) for part in parents] + [
        (0 if row["entity_type"] == "task" else 1, name)
    ]


def _cell(
    row: dict[str, Any], column: ExportColumn, labels: bool, users: dict[str, str]
) -> Cell:
    value = row.get(column.key)
    if labels and column.key in DISPLAY_KEYS:
        value = row.get(DISPLAY_KEYS[column.key]) or value
    if isinstance(value, list):
        items = [_value(item, column, labels, users) for item in value]
        return ", ".join(str(item) for item in items if item is not None) or None
    return _value(value, column, labels, users)


def _value(value: Any, column: ExportColumn, labels: bool, users: dict[str, str]):
    if value is None or value == "":
        return None
    if isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return int(value) if labels and value.is_integer() else value
    if isinstance(value, dict):
        return json.dumps(value)
    value = str(value)
    if labels:
        if column.users:
            return users.get(value, value)
        if column.enum_labels:
            return column.enum_labels.get(value, value)
        if column.value_type == "datetime":
            return _readable_datetime(value)
    return value


def _readable_datetime(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if (moment.hour, moment.minute, moment.second) == (0, 0, 0):
        return moment.date().isoformat()
    return moment.strftime("%Y-%m-%d %H:%M")


def _text(cell: Cell, labels: bool) -> str:
    """CSV text, raw values are written the way the importer reads them back."""
    if cell is None:
        return ""
    if isinstance(cell, bool):
        if labels:
            return "Yes" if cell else "No"
        return "true" if cell else "false"
    return str(cell)


def _unique(labels: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for label in labels:
        seen[label] = seen.get(label, 0) + 1
        result.append(label if seen[label] == 1 else f"{label} ({seen[label]})")
    return result

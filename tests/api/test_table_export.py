"""Table export: POST /api/export-table.

Black-box tests of the export endpoint: they only use HTTP, so the same tests
check the feature after it moves. `AYON_EXPORT_TABLE_URL` overrides the
endpoint path (by default `/api/export-table`).

The fixture project (one per module):

    assets               fps 25, priority high, startDate 2026-10-08
      chars
        hero             label "Hero Character", tags, description with quotes
          modeling       task, label "Modeling", assigned, fps 30
          rigging        task
          modelMain      product (model), productGroup "grp", versions v001 v002
                         (v002 has an exr representation)
          rigMain        product (rig), version v001
      props
    shots                fps 24
      sh010              description "=1+2"
        comp             task

Users: `assignee` (full name "Export Tester") is assigned to modeling and is
limited by an access group to /assets and the fps attribute.
`outsider` has no access to the project.
"""

import csv
import io
import json
import os
import uuid
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

import httpx
import pytest

from .conftest import API_URL, TempProject, create_temp_project

EXPORT_URL = os.environ.get("AYON_EXPORT_TABLE_URL", "/api/export-table")
PASSWORD = "Api-test-1234!"
XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

DESCRIPTION = 'Says "hi", then\nleaves; costs 5€, ünïcödé'


def new_id() -> str:
    return uuid.uuid4().hex


#
# Helpers
#


def export(api: httpx.Client, project_name: str, **payload: Any) -> httpx.Response:
    return api.post(EXPORT_URL, json={"projectName": project_name, **payload})


def read_csv(response: httpx.Response, delimiter: str = ",") -> list[list[str]]:
    assert response.status_code == 200, response.text
    text = response.content.decode("utf-8")
    assert text.startswith("﻿"), "CSV must start with a BOM for Excel"
    return list(csv.reader(io.StringIO(text[1:]), delimiter=delimiter))


def as_dicts(table: list[list[str]]) -> list[dict[str, str]]:
    header, *rows = table
    return [dict(zip(header, row, strict=True)) for row in rows]


def export_rows(api: httpx.Client, project_name: str, **payload: Any):
    """Export as CSV with key headers, rows as dicts."""
    payload.setdefault("header", "key")
    return as_dicts(read_csv(export(api, project_name, **payload)))


def column_index(ref: str) -> int:
    letters = "".join(c for c in ref if c.isalpha())
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index - 1


def read_xlsx(content: bytes) -> list[list[Any]]:
    """Cells of the first sheet (numbers as numbers, booleans as bools)."""
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        names = set(package.namelist())
        for part in (
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
            "xl/styles.xml",
        ):
            assert part in names, f"missing {part}"
            ElementTree.fromstring(package.read(part))  # well-formed
        sheet = ElementTree.fromstring(package.read("xl/worksheets/sheet1.xml"))
    table: list[list[Any]] = []
    for row in sheet.iterfind("m:sheetData/m:row", XLSX_NS):
        cells: list[Any] = []
        for cell in row.iterfind("m:c", XLSX_NS):
            index = column_index(cell.get("r", ""))
            cells.extend([None] * (index - len(cells) + 1))
            kind = cell.get("t")
            if kind == "inlineStr":
                value: Any = "".join(cell.find("m:is", XLSX_NS).itertext())  # type: ignore
            elif kind == "b":
                value = cell.findtext("m:v", namespaces=XLSX_NS) == "1"
            else:
                text = cell.findtext("m:v", namespaces=XLSX_NS) or ""
                value = float(text) if any(c in text for c in ".eE") else int(text)
            cells[index] = value
        table.append(cells)
    width = max(len(row) for row in table)
    return [row + [None] * (width - len(row)) for row in table]


def login(name: str) -> httpx.Client:
    response = httpx.post(
        f"{API_URL}/api/auth/login", json={"name": name, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return httpx.Client(
        base_url=API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=120
    )


def create_user(api: httpx.Client, full_name: str) -> str:
    name = f"apitest{uuid.uuid4().hex[:8]}"
    response = api.put(
        f"/api/users/{name}",
        json={"attrib": {"fullName": full_name}, "password": PASSWORD},
    )
    assert response.status_code == 204, response.text
    return name


#
# Fixture
#


@dataclass
class ExportFixture:
    project: TempProject
    folders: dict[str, str]
    tasks: dict[str, str]
    products: dict[str, str]
    versions: dict[str, str]
    assignee: str
    outsider: str
    access_group: str
    list_id: str
    list_items: dict[str, str]

    @property
    def name(self) -> str:
        return self.project.name

    @property
    def api(self) -> httpx.Client:
        return self.project.api

    @property
    def all_folders(self) -> list[str]:
        return list(self.folders.values())

    def rows(self, **payload: Any) -> list[dict[str, str]]:
        return export_rows(self.api, self.name, **payload)


def build_fixture(project: TempProject, api: httpx.Client) -> ExportFixture:
    folder_type = project.folder_types[0]
    task_type = project.task_types[0]
    assignee = create_user(api, "Export Tester")
    outsider = create_user(api, "Outsider")
    # (users and the access group are deleted by the fx fixture)

    def folder(name: str, parent: str | None = None, **data: Any) -> str:
        return project.create(
            "folder", name=name, folderType=folder_type, parentId=parent, **data
        )

    folders: dict[str, str] = {}
    folders["assets"] = folder(
        "assets",
        attrib={
            "fps": 25.0,
            "priority": "high",
            "startDate": "2026-10-08T00:00:00+00:00",
        },
    )
    folders["chars"] = folder("chars", folders["assets"])
    folders["hero"] = folder(
        "hero",
        folders["chars"],
        label="Hero Character",
        tags=["main", "rig"],
        status=project.statuses[1],
        attrib={"description": DESCRIPTION},
    )
    folders["props"] = folder("props", folders["assets"])
    folders["shots"] = folder("shots", attrib={"fps": 24.0})
    folders["sh010"] = folder("sh010", folders["shots"], attrib={"description": "=1+2"})

    tasks = {
        "modeling": project.create(
            "task",
            name="modeling",
            label="Modeling",
            taskType=task_type,
            folderId=folders["hero"],
            assignees=[assignee],
            attrib={"fps": 30.0},
        ),
        "rigging": project.create(
            "task", name="rigging", taskType=task_type, folderId=folders["hero"]
        ),
        "comp": project.create(
            "task", name="comp", taskType=task_type, folderId=folders["sh010"]
        ),
    }

    products = {
        "modelMain": project.create(
            "product",
            name="modelMain",
            productType="model",
            folderId=folders["hero"],
            attrib={"productGroup": "grp"},
        ),
        "rigMain": project.create(
            "product", name="rigMain", productType="rig", folderId=folders["hero"]
        ),
    }
    versions = {
        "modelMain/v001": project.create(
            "version",
            version=1,
            productId=products["modelMain"],
            taskId=tasks["modeling"],
            author=assignee,
            attrib={"comment": "first"},
        ),
        "modelMain/v002": project.create(
            "version", version=2, productId=products["modelMain"], author=assignee
        ),
        "rigMain/v001": project.create(
            "version", version=1, productId=products["rigMain"], author=assignee
        ),
    }

    project.create(
        "representation", name="exr", versionId=versions["modelMain/v002"], files=[]
    )

    # A folder list: sh010, then hero (with a list attribute and an fps override)
    list_id = new_id()
    list_items = {"sh010": new_id(), "hero": new_id()}
    response = api.post(
        f"/api/projects/{project.name}/lists",
        json={
            "id": list_id,
            "label": "export test",
            "entityType": "folder",
            "items": [
                {"id": list_items["sh010"], "entityId": folders["sh010"]},
                {
                    "id": list_items["hero"],
                    "entityId": folders["hero"],
                    "attrib": {"fps": 60.0, "listNote": "note"},
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    response = api.put(
        f"/api/projects/{project.name}/lists/{list_id}/attributes",
        json=[{"name": "listNote", "data": {"type": "string", "title": "List note"}}],
    )
    assert response.status_code == 200, response.text

    # assignee: /assets only, and only the fps attribute
    access_group = f"apitest{uuid.uuid4().hex[:8]}"
    response = api.put(
        f"/api/accessGroups/{access_group}/_",
        json={
            "read": {
                "enabled": True,
                "access_list": [{"access_type": "hierarchy", "path": "/assets"}],
            },
            "attrib_read": {"enabled": True, "attributes": ["fps"]},
        },
    )
    assert response.status_code == 204, response.text
    response = api.patch(
        f"/api/users/{assignee}/accessGroups",
        json={
            "accessGroups": [{"project": project.name, "accessGroups": [access_group]}]
        },
    )
    assert response.status_code == 204, response.text

    return ExportFixture(
        project=project,
        folders=folders,
        tasks=tasks,
        products=products,
        versions=versions,
        assignee=assignee,
        outsider=outsider,
        access_group=access_group,
        list_id=list_id,
        list_items=list_items,
    )


@pytest.fixture(scope="module")
def fx(api: httpx.Client) -> Iterator[ExportFixture]:
    with create_temp_project(api) as project:
        fixture = build_fixture(project, api)
        try:
            yield fixture
        finally:
            api.delete(f"/api/users/{fixture.assignee}")
            api.delete(f"/api/users/{fixture.outsider}")
            api.delete(f"/api/accessGroups/{fixture.access_group}/_")


def hierarchy(fx: ExportFixture, **payload: Any) -> dict[str, Any]:
    """Payload exporting all folders and tasks."""
    return {"folderIds": fx.all_folders, "tasks": {}, **payload}


#
# Request validation and access
#


def test_unknown_column_is_rejected(fx: ExportFixture):
    response = export(fx.api, fx.name, columns=["name", "nonsense"], folderIds=[])
    assert response.status_code == 400
    assert "nonsense" in response.text


@pytest.mark.xfail(
    strict=True,
    reason="BUG: any attrib.* key is accepted and exported as an empty column",
)
def test_unknown_attribute_is_rejected(fx: ExportFixture):
    """A misspelled attribute is an unknown column, not an empty one.

    (List attributes are known when the list is exported.)
    """
    response = export(fx.api, fx.name, columns=["attrib.fsp"], folderIds=[])
    assert response.status_code == 400


def test_unknown_project(fx: ExportFixture):
    response = export(fx.api, "no_such_project_x", columns=["name"])
    assert response.status_code == 404


def test_user_without_project_access_is_refused(fx: ExportFixture):
    with login(fx.outsider) as client:
        response = export(client, fx.name, columns=["name"], **hierarchy(fx))
    assert response.status_code in (403, 404), response.text


def test_duplicate_columns_are_exported_once(fx: ExportFixture):
    table = read_csv(
        export(
            fx.api,
            fx.name,
            columns=["name", "name", "path"],
            header="key",
            folderIds=[fx.folders["hero"]],
        )
    )
    assert table == [["name", "path"], ["hero", "assets/chars/hero"]]


def test_no_rows(fx: ExportFixture):
    table = read_csv(export(fx.api, fx.name, columns=["name"], header="key"))
    assert table == [["name"]]


#
# File formats
#


def test_csv_file(fx: ExportFixture):
    response = export(fx.api, fx.name, columns=["name"], folderIds=[])
    assert response.headers["content-type"].startswith("text/csv")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert f'filename="{fx.name}_export_' in disposition
    assert disposition.endswith('.csv"')


@pytest.mark.parametrize(
    ("delimiter", "extension"), [(",", "csv"), (";", "csv"), ("\t", "tsv")]
)
def test_csv_delimiters(fx: ExportFixture, delimiter: str, extension: str):
    response = export(
        fx.api,
        fx.name,
        columns=["name", "attrib.description"],
        header="key",
        delimiter=delimiter,
        folderIds=[fx.folders["hero"]],
    )
    assert response.headers["content-disposition"].endswith(f'.{extension}"')
    assert response.headers["content-type"].startswith(f"text/{extension}")
    table = read_csv(response, delimiter)
    assert table == [["name", "attrib.description"], ["hero", DESCRIPTION]]


def test_xlsx_file(fx: ExportFixture):
    response = export(
        fx.api,
        fx.name,
        columns=["name", "label", "active", "attrib.fps", "attrib.description"],
        header="key",
        format="xlsx",
        folderIds=[fx.folders["hero"], fx.folders["assets"]],
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"].endswith('.xlsx"')
    table = read_xlsx(response.content)
    assert table[0] == ["name", "label", "active", "attrib.fps", "attrib.description"]
    rows = {row[0]: row for row in table[1:]}
    assert rows["hero"] == ["hero", "Hero Character", True, 25.0, DESCRIPTION]
    assert rows["assets"][3] == 25.0  # a number, not text


def test_xlsx_matches_csv(fx: ExportFixture):
    payload = hierarchy(
        fx,
        columns=["entity_type", "path", "name", "status", "tags", "assignees"],
        values="label",
    )
    csv_table = read_csv(export(fx.api, fx.name, **payload))
    xlsx_table = read_xlsx(export(fx.api, fx.name, format="xlsx", **payload).content)
    as_text = [
        ["" if cell is None else str(cell) for cell in row] for row in xlsx_table
    ]
    assert as_text == csv_table


def test_xlsx_many_columns(fx: ExportFixture):
    """Column letters past Z (AA, AB...) and the filter range."""
    response = export(
        fx.api,
        fx.name,
        columns=[
            "name",
            "path",
            "id",
            "label",
            "status",
            "tags",
            "active",
            "entity_type",
            "created_at",
            "updated_at",
            "attrib.fps",
            "attrib.priority",
            "attrib.frameStart",
            "attrib.frameEnd",
            "attrib.handleStart",
            "attrib.handleEnd",
            "attrib.resolutionWidth",
            "attrib.resolutionHeight",
            "attrib.pixelAspect",
            "attrib.clipIn",
            "attrib.clipOut",
            "attrib.startDate",
            "attrib.endDate",
            "attrib.description",
            "folder_type",
            "parent_id",
            "folder.status",
            "folder.tags",
            "folder.attrib.fps",
        ],
        header="key",
        format="xlsx",
        folderIds=[fx.folders["hero"]],
    )
    table = read_xlsx(response.content)
    assert len(table[0]) == 29
    assert table[0][-1] == "folder.attrib.fps"
    assert table[1][0] == "hero"


def test_xlsx_control_characters(fx: ExportFixture):
    """Characters XML does not allow are dropped, the file stays valid."""
    project = fx.project
    folder_id = project.create(
        "folder",
        name="ctrl",
        folderType=project.folder_types[0],
        attrib={"description": "a\x0bb\x01c\x1fd\te\nf"},
    )
    try:
        response = export(
            fx.api,
            fx.name,
            columns=["attrib.description"],
            header="key",
            format="xlsx",
            folderIds=[folder_id],
        )
        assert read_xlsx(response.content)[1] == ["abcd\te\nf"]
    finally:
        project.op("delete", "folder", folder_id)


#
# Hierarchy rows
#


def test_tree_order(fx: ExportFixture):
    """Depth first, a folder's tasks before its subfolders."""
    rows = fx.rows(**hierarchy(fx, columns=["path"]))
    assert [row["path"] for row in rows] == [
        "assets",
        "assets/chars",
        "assets/chars/hero",
        "assets/chars/hero/modeling",
        "assets/chars/hero/rigging",
        "assets/props",
        "shots",
        "shots/sh010",
        "shots/sh010/comp",
    ]


def test_tree_order_tasks_before_subfolders(fx: ExportFixture):
    project = fx.project
    task_id = project.create(
        "task",
        name="zzz_layout",
        taskType=project.task_types[0],
        folderId=fx.folders["assets"],
    )
    try:
        rows = fx.rows(**hierarchy(fx, columns=["path"]))
        paths = [row["path"] for row in rows]
        assert paths.index("assets/zzz_layout") == 1  # before assets/chars
    finally:
        project.op("delete", "task", task_id)


def test_raw_values(fx: ExportFixture):
    columns = [
        "entity_type",
        "path",
        "name",
        "label",
        "folder_or_task_type",
        "status",
        "tags",
        "active",
        "assignees",
        "attrib.fps",
        "attrib.priority",
        "attrib.startDate",
    ]
    rows = {row["path"]: row for row in fx.rows(**hierarchy(fx, columns=columns))}
    hero = rows["assets/chars/hero"]
    assert hero["entity_type"] == "folder"
    assert hero["name"] == "hero"
    assert hero["label"] == "Hero Character"
    assert hero["folder_or_task_type"] == fx.project.folder_types[0]
    assert hero["status"] == fx.project.statuses[1]
    assert hero["tags"] == "main, rig"
    assert hero["active"] == "true"

    modeling = rows["assets/chars/hero/modeling"]
    assert modeling["entity_type"] == "task"
    assert modeling["assignees"] == fx.assignee
    assert modeling["folder_or_task_type"] == fx.project.task_types[0]
    assert modeling["attrib.fps"] == "30.0"

    assets = rows["assets"]
    assert assets["attrib.priority"] == "high"
    assert assets["attrib.startDate"].startswith("2026-10-08")


def test_inherited_attributes(fx: ExportFixture):
    rows = {
        row["path"]: row
        for row in fx.rows(**hierarchy(fx, columns=["path", "attrib.fps"]))
    }
    assert rows["assets/chars/hero"]["attrib.fps"] == "25.0"
    assert rows["assets/chars/hero/rigging"]["attrib.fps"] == "25.0"
    assert rows["assets/chars/hero/modeling"]["attrib.fps"] == "30.0"  # own value
    assert rows["shots/sh010/comp"]["attrib.fps"] == "24.0"


def test_label_values(fx: ExportFixture):
    columns = [
        "entity_type",
        "path",
        "name",
        "active",
        "assignees",
        "attrib.fps",
        "attrib.priority",
        "attrib.startDate",
        "created_at",
    ]
    rows = fx.rows(**hierarchy(fx, columns=columns, values="label"))
    by_path = {row["path"]: row for row in rows}

    hero = by_path["assets/chars/hero"]
    assert hero["entity_type"] == "Folder"
    assert hero["name"] == "Hero Character"
    assert hero["active"] == "Yes"
    assert hero["attrib.fps"] == "25"  # whole floats without ".0"

    modeling = by_path["assets/chars/hero/modeling"]
    assert modeling["entity_type"] == "Task"
    assert modeling["name"] == "Modeling"
    assert modeling["assignees"] == "Export Tester"

    assets = by_path["assets"]
    assert assets["name"] == "assets"  # no label: the name
    assert assets["attrib.priority"] == "High"
    assert assets["attrib.startDate"] == "2026-10-08"
    # readable: "2026-10-22 14:05"
    assert len(assets["created_at"]) == 16, assets["created_at"]


def test_header_labels(fx: ExportFixture):
    table = read_csv(
        export(
            fx.api,
            fx.name,
            columns=["entity_type", "folder_or_task_type", "attrib.fps", "name"],
            folderIds=[],
        )
    )
    header = table[0]
    assert header[0] != "entity_type"
    assert header[1] == "Type"
    assert header[2] == "FPS"


def test_column_labels_and_unique_headers(fx: ExportFixture):
    table = read_csv(
        export(
            fx.api,
            fx.name,
            columns=["name", "label", "path"],
            columnLabels={"name": "Thing", "label": "Thing"},
            folderIds=[],
        )
    )
    assert table[0][:2] == ["Thing", "Thing (2)"]


def test_parent_columns(fx: ExportFixture):
    columns = [
        "path",
        "folder",
        "folder.status",
        "folder.tags",
        "folder.attrib.fps",
        "folder.attrib.description",
    ]
    rows = fx.rows(tasks={"ids": [fx.tasks["modeling"]]}, columns=columns)
    assert rows == [
        {
            "path": "assets/chars/hero/modeling",
            "folder": "hero",
            "folder.status": fx.project.statuses[1],
            "folder.tags": "main, rig",
            "folder.attrib.fps": "25.0",
            "folder.attrib.description": DESCRIPTION,
        }
    ]


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("folder.name", "hero"),
        ("folder.label", "Hero Character"),
        ("folder.path", "assets/chars/hero"),
        ("folder.folder_type", None),  # filled in the test
    ],
)
def test_accepted_parent_columns_have_values(
    fx: ExportFixture, column: str, expected: str | None
):
    """A parent column the endpoint accepts must not come out empty."""
    if expected is None:
        expected = fx.project.folder_types[0]
    rows = fx.rows(tasks={"ids": [fx.tasks["modeling"]]}, columns=[column])
    assert rows == [{column: expected}]


def test_version_parent_names(fx: ExportFixture):
    columns = [
        "folder.name",
        "folder.path",
        "product.name",
        "product.path",
        "task.name",
        "task.label",
    ]
    rows = fx.rows(versions={"ids": [fx.versions["modelMain/v001"]]}, columns=columns)
    assert rows == [
        {
            "folder.name": "hero",
            "folder.path": "assets/chars/hero",
            "product.name": "modelMain",
            "product.path": "assets/chars/hero/modelMain",
            "task.name": "modeling",
            "task.label": "Modeling",
        }
    ]
    rows = fx.rows(
        versions={"ids": [fx.versions["modelMain/v001"]]},
        columns=["folder.name", "task.name"],
        values="label",
    )
    assert rows == [{"folder.name": "Hero Character", "task.name": "Modeling"}]


@pytest.mark.parametrize(
    "column", ["task.path", "product.label", "folder.assignees", "folder.folder"]
)
def test_parent_columns_without_values_are_rejected(fx: ExportFixture, column: str):
    response = export(fx.api, fx.name, columns=[column], folderIds=[])
    assert response.status_code == 400, response.text


def test_parent_header_labels(fx: ExportFixture):
    table = read_csv(
        export(fx.api, fx.name, columns=["folder.attrib.fps"], folderIds=[])
    )
    assert table[0] == ["Folder FPS"]


#
# Task queries
#


def test_selected_tasks(fx: ExportFixture):
    rows = fx.rows(
        tasks={"ids": [fx.tasks["comp"], fx.tasks["rigging"]]}, columns=["path"]
    )
    assert [row["path"] for row in rows] == [
        "assets/chars/hero/rigging",
        "shots/sh010/comp",
    ]


def test_empty_task_selection_exports_no_tasks(fx: ExportFixture):
    rows = fx.rows(
        folderIds=[fx.folders["hero"]], tasks={"ids": []}, columns=["entity_type"]
    )
    assert rows == [{"entity_type": "folder"}]


def test_tasks_of_folders(fx: ExportFixture):
    rows = fx.rows(tasks={"folderIds": [fx.folders["assets"]]}, columns=["name"])
    assert sorted(row["name"] for row in rows) == ["modeling", "rigging"]

    rows = fx.rows(
        tasks={"folderIds": [fx.folders["assets"]], "includeFolderChildren": False},
        columns=["name"],
    )
    assert rows == []


def test_task_filter(fx: ExportFixture):
    task_filter = (
        '{"conditions": [{"key": "name", "operator": "eq", "value": "modeling"}]}'
    )
    rows = fx.rows(tasks={"filter": task_filter}, columns=["name"])
    assert rows == [{"name": "modeling"}]


def test_task_search(fx: ExportFixture):
    rows = fx.rows(tasks={"search": "rigging"}, columns=["name"])
    assert [row["name"] for row in rows] == ["rigging"]


def test_sorted_tasks_keep_the_query_order(fx: ExportFixture):
    """Task list views (flat, grouped) export in the order of the table."""
    rows = fx.rows(tasks={"sortBy": ["-name"]}, columns=["name"])
    assert [row["name"] for row in rows] == ["rigging", "modeling", "comp"]


def test_sorted_tasks_follow_the_folders(fx: ExportFixture):
    rows = fx.rows(
        folderIds=[fx.folders["hero"], fx.folders["sh010"]],
        tasks={"sortBy": ["name"]},
        columns=["path"],
    )
    assert [row["path"] for row in rows] == [
        "assets/chars/hero",
        "shots/sh010",
        "shots/sh010/comp",
        "assets/chars/hero/modeling",
        "assets/chars/hero/rigging",
    ]


def test_invalid_filter_is_a_bad_request(fx: ExportFixture):
    response = export(fx.api, fx.name, columns=["name"], tasks={"filter": "{nope"})
    assert response.status_code == 400, response.text


#
# Products and versions
#


def test_products_with_versions(fx: ExportFixture):
    """Versions follow their product, as in the products table."""
    columns = ["entity_type", "path", "product", "version", "author"]
    rows = fx.rows(
        products={"folderIds": [fx.folders["hero"]]}, versions={}, columns=columns
    )
    assert [(row["entity_type"], row["path"]) for row in rows] == [
        ("product", "assets/chars/hero/modelMain"),
        ("version", "assets/chars/hero/modelMain/v001"),
        ("version", "assets/chars/hero/modelMain/v002"),
        ("product", "assets/chars/hero/rigMain"),
        ("version", "assets/chars/hero/rigMain/v001"),
    ]
    product = rows[0]
    assert product["version"] == "v002"  # featured: latest
    assert product["author"] == fx.assignee
    assert rows[1]["product"] == "modelMain"
    assert rows[1]["version"] == "v001"


def test_products_with_versions_keep_product_order(fx: ExportFixture):
    """The products table sorted by name descending exports in that order."""
    rows = fx.rows(
        products={"folderIds": [fx.folders["hero"]], "sortBy": ["-name"]},
        versions={},
        columns=["entity_type", "path"],
    )
    assert [row["path"] for row in rows if row["entity_type"] == "product"] == [
        "assets/chars/hero/rigMain",
        "assets/chars/hero/modelMain",
    ]


def test_versions_follow_their_product_in_version_order(fx: ExportFixture):
    rows = fx.rows(
        products={"folderIds": [fx.folders["hero"]], "sortBy": ["name"]},
        versions={"sortBy": ["-version"]},
        columns=["path"],
    )
    assert [row["path"] for row in rows] == [
        "assets/chars/hero/modelMain",
        "assets/chars/hero/modelMain/v002",
        "assets/chars/hero/modelMain/v001",
        "assets/chars/hero/rigMain",
        "assets/chars/hero/rigMain/v001",
    ]


def test_representation_filter(fx: ExportFixture):
    """Only products and versions with an exr representation, as in the table."""
    exr = json.dumps(
        {"conditions": [{"key": "name", "operator": "eq", "value": "exr"}]}
    )
    rows = fx.rows(
        products={"folderIds": [fx.folders["hero"]], "representationFilter": exr},
        versions={"representationFilter": exr},
        columns=["path"],
    )
    assert [row["path"] for row in rows] == [
        "assets/chars/hero/modelMain",
        "assets/chars/hero/modelMain/v002",
    ]


def test_folder_column_labels(fx: ExportFixture):
    rows = fx.rows(
        tasks={"ids": [fx.tasks["modeling"]]},
        versions={"ids": [fx.versions["modelMain/v001"]]},
        columns=["entity_type", "folder"],
        values="label",
    )
    assert rows == [
        {"entity_type": "Task", "folder": "Hero Character"},
        {"entity_type": "Version", "folder": "Hero Character"},
    ]


def test_products_and_versions_folder_type(fx: ExportFixture):
    """The products table's folder type column is exported as folder_type."""
    rows = fx.rows(
        products={"ids": [fx.products["rigMain"]]},
        versions={},
        columns=["entity_type", "folder_type"],
    )
    folder_type = fx.project.folder_types[0]
    assert rows == [
        {"entity_type": "product", "folder_type": folder_type},
        {"entity_type": "version", "folder_type": folder_type},
    ]


def test_product_column_of_products(fx: ExportFixture):
    """The products table's product name column is exported as product."""
    rows = fx.rows(
        products={"ids": [fx.products["rigMain"]]},
        versions={},
        columns=["entity_type", "product"],
    )
    assert rows == [
        {"entity_type": "product", "product": "rigMain"},
        {"entity_type": "version", "product": "rigMain"},
    ]


def test_versions_of_selected_products_only(fx: ExportFixture):
    rows = fx.rows(
        products={"ids": [fx.products["rigMain"]]}, versions={}, columns=["path"]
    )
    assert [row["path"] for row in rows] == [
        "assets/chars/hero/rigMain",
        "assets/chars/hero/rigMain/v001",
    ]


def test_no_products_means_no_versions(fx: ExportFixture):
    rows = fx.rows(products={"ids": []}, versions={}, columns=["path"])
    assert rows == []


def test_selected_versions(fx: ExportFixture):
    rows = fx.rows(
        versions={"ids": [fx.versions["modelMain/v002"]]},
        columns=["path", "product", "folder", "product_type"],
    )
    assert rows == [
        {
            "path": "assets/chars/hero/modelMain/v002",
            "product": "modelMain",
            "folder": "hero",
            "product_type": "model",
        }
    ]


def test_version_parent_columns(fx: ExportFixture):
    rows = fx.rows(
        versions={"ids": [fx.versions["modelMain/v001"]]},
        columns=[
            "task",
            "task_type",
            "product.attrib.productGroup",
            "folder.attrib.fps",
            "attrib.comment",
        ],
    )
    assert rows == [
        {
            "task": "modeling",
            "task_type": fx.project.task_types[0],
            "product.attrib.productGroup": "grp",
            "folder.attrib.fps": "25.0",
            "attrib.comment": "first",
        }
    ]


def test_version_label_is_product_and_version(fx: ExportFixture):
    rows = fx.rows(
        versions={"ids": [fx.versions["modelMain/v001"]]},
        columns=["name", "task", "author"],
        values="label",
    )
    assert rows == [
        {"name": "modelMain v001", "task": "Modeling", "author": "Export Tester"}
    ]


def test_versions_keep_query_order(fx: ExportFixture):
    rows = fx.rows(
        versions={"productIds": [fx.products["modelMain"]], "sortBy": ["-version"]},
        columns=["version"],
    )
    assert [row["version"] for row in rows] == ["v002", "v001"]


def test_featured_only(fx: ExportFixture):
    rows = fx.rows(
        versions={"folderIds": [fx.folders["hero"]], "featuredOnly": ["latest"]},
        columns=["path"],
    )
    assert sorted(row["path"] for row in rows) == [
        "assets/chars/hero/modelMain/v002",
        "assets/chars/hero/rigMain/v001",
    ]


#
# Entity lists
#


def test_list_items(fx: ExportFixture):
    rows = fx.rows(
        entityList={"id": fx.list_id},
        columns=["name", "attrib.fps", "attrib.listNote"],
    )
    # in list order, item values over the entity's
    assert rows == [
        {"name": "sh010", "attrib.fps": "24.0", "attrib.listNote": ""},
        {"name": "hero", "attrib.fps": "60.0", "attrib.listNote": "note"},
    ]


def test_list_attribute_header(fx: ExportFixture):
    table = read_csv(
        export(
            fx.api,
            fx.name,
            entityList={"id": fx.list_id},
            columns=["attrib.listNote"],
        )
    )
    assert table[0] == ["List note"]


def test_selected_list_items(fx: ExportFixture):
    rows = fx.rows(
        entityList={"id": fx.list_id, "itemIds": [fx.list_items["hero"]]},
        columns=["name"],
    )
    assert rows == [{"name": "hero"}]


def test_unknown_list(fx: ExportFixture):
    response = export(fx.api, fx.name, entityList={"id": new_id()}, columns=["name"])
    assert response.status_code in (400, 404), response.text


#
# Permissions
#


def test_restricted_user_gets_readable_folders_only(fx: ExportFixture):
    with login(fx.assignee) as client:
        rows = export_rows(client, fx.name, **hierarchy(fx, columns=["path"]))
    paths = [row["path"] for row in rows]
    assert paths
    assert all(path.startswith("assets") for path in paths), paths
    assert "assets/chars/hero/modeling" in paths


def test_restricted_user_gets_readable_attributes_only(fx: ExportFixture):
    with login(fx.assignee) as client:
        rows = export_rows(
            client,
            fx.name,
            folderIds=[fx.folders["hero"]],
            columns=["attrib.fps", "attrib.description", "attrib.priority"],
        )
    assert rows == [
        {"attrib.fps": "25.0", "attrib.description": "", "attrib.priority": ""}
    ]


def test_restricted_user_parent_attributes(fx: ExportFixture):
    with login(fx.assignee) as client:
        rows = export_rows(
            client,
            fx.name,
            tasks={"ids": [fx.tasks["modeling"]]},
            columns=["folder.attrib.description", "folder.attrib.fps"],
        )
    assert rows == [{"folder.attrib.description": "", "folder.attrib.fps": "25.0"}]


def test_restricted_user_versions(fx: ExportFixture):
    with login(fx.assignee) as client:
        rows = export_rows(
            client,
            fx.name,
            versions={"ids": list(fx.versions.values())},
            columns=["path", "attrib.comment", "product.attrib.productGroup"],
        )
    assert len(rows) == 3
    assert all(row["attrib.comment"] == "" for row in rows)
    assert all(row["product.attrib.productGroup"] == "" for row in rows)


def test_restricted_user_list_items(fx: ExportFixture):
    with login(fx.assignee) as client:
        rows = export_rows(
            client,
            fx.name,
            entityList={"id": fx.list_id},
            columns=["name", "attrib.listNote", "attrib.fps"],
        )
    assert [row["name"] for row in rows] == ["hero"]  # sh010 is not readable


def test_restricted_user_names_in_labels(fx: ExportFixture):
    """Full names of assignees, as far as the user can see them."""
    with login(fx.assignee) as client:
        rows = export_rows(
            client,
            fx.name,
            tasks={"ids": [fx.tasks["modeling"]]},
            columns=["assignees"],
            values="label",
        )
    assert rows == [{"assignees": "Export Tester"}]


#
# Round trip through the importer
#


def import_csv(
    api: httpx.Client, project_name: str, content: bytes, preview: bool
) -> dict[str, Any]:
    response = api.put(
        "/api/csv/import/upload",
        content=content,
        headers={"Content-Type": "text/csv"},
    )
    assert response.status_code == 200, response.text
    file_id = response.json()["id"]
    header = next(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    mapping = [
        {
            "sourceKey": key,
            "targetKey": key,
            "action": "map",
            "errorHandlingMode": "abort",
            "valuesMapping": [],
        }
        for key in header
    ]
    response = api.post(
        "/api/csv/import/hierarchy",
        params={"file_id": file_id, "project_name": project_name, "preview": preview},
        json=mapping,
    )
    assert response.status_code == 200, response.text
    return response.json()


IMPORT_COLUMNS = [
    "entity_type",
    "path",
    "name",
    "label",
    "folder_or_task_type",
    "status",
    "tags",
    "assignees",
    "attrib.fps",
    "attrib.priority",
    "attrib.description",
    "attrib.startDate",
]


def test_raw_export_imports_back(fx: ExportFixture):
    columns = [c for c in IMPORT_COLUMNS if c != "tags"]
    content = export(
        fx.api, fx.name, **hierarchy(fx, columns=columns, header="key")
    ).content
    result = import_csv(fx.api, fx.name, content, preview=True)
    assert result["failed"] == 0, result["failedItems"]
    assert result["created"] == 0, result
    assert result["updated"] == 9, result


@pytest.mark.xfail(
    strict=True,
    reason="BUG: the importer rejects entity tags missing from the anatomy",
)
def test_raw_export_with_tags_imports_back(fx: ExportFixture):
    """hero has tags that are not in the project anatomy (the API allows it)."""
    content = export(
        fx.api, fx.name, **hierarchy(fx, columns=IMPORT_COLUMNS, header="key")
    ).content
    result = import_csv(fx.api, fx.name, content, preview=True)
    assert result["failed"] == 0, result["failedItems"]


@pytest.mark.xfail(
    strict=True,
    reason="BUG: inherited values are exported, imported back they become own",
)
def test_round_trip_keeps_inheritance(api: httpx.Client):
    """Exporting and importing back unchanged must not change the project:
    inherited attribute values must stay inherited."""
    with create_temp_project(api) as project:
        parent = project.create(
            "folder",
            name="seq",
            folderType=project.folder_types[0],
            attrib={"fps": 50.0},
        )
        child = project.create(
            "folder", name="sh010", folderType=project.folder_types[0], parentId=parent
        )
        content = export(
            api,
            project.name,
            folderIds=[parent, child],
            columns=[
                "entity_type",
                "path",
                "name",
                "folder_or_task_type",
                "attrib.fps",
            ],
            header="key",
        ).content
        result = import_csv(api, project.name, content, preview=False)
        assert result["failed"] == 0, result["failedItems"]

        own = project.get("folder", child)["ownAttrib"]
        assert "fps" not in own, "the inherited fps became an own value"

        # still follows the parent
        project.op("update", "folder", parent, data={"attrib": {"fps": 25.0}})
        assert project.get("folder", child)["attrib"]["fps"] == 25.0


#
# Pagination
#


def test_more_rows_than_a_page(api: httpx.Client):
    """Exports are not cut at the page size of the GraphQL queries (2000)."""
    count = 2005
    with create_temp_project(api) as project:
        folder_id = project.create(
            "folder", name="many", folderType=project.folder_types[0]
        )
        operations = [
            {
                "type": "create",
                "entityType": "task",
                "data": {
                    "name": f"t{i:05d}",
                    "taskType": project.task_types[0],
                    "folderId": folder_id,
                },
            }
            for i in range(count)
        ]
        for start in range(0, count, 500):
            project.ops(*operations[start : start + 500])
        rows = export_rows(api, project.name, tasks={}, columns=["name"])
        names = [row["name"] for row in rows]
        assert len(names) == count
        assert len(set(names)) == count

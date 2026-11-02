"""Unit tests of the Documents helper with a mocked database."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from ayon_server import documents as documents_module
from ayon_server.documents import DocumentRecord, Documents
from ayon_server.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.sqlfilter import QueryCondition, QueryFilter

DOC_ID = "0123456789abcdef0123456789abcdef"
KIND = "io.ynput.reports.chart"


def _row(**kwargs: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    row = {
        "id": DOC_ID,
        "kind": KIND,
        "label": "Chart",
        "data": {},
        "payload": {},
        "access": {},
        "created_at": now,
        "updated_at": now,
        "created_by": "alice",
        "updated_by": "alice",
    }
    row.update(kwargs)
    return row


@pytest.fixture
def db(monkeypatch):
    """Record queries; `db.result` is returned by fetchrow."""
    state = SimpleNamespace(calls=[], result=None, rows=[])

    async def fetchrow(query: str, *args: Any, **kwargs: Any):
        state.calls.append((query, args))
        return state.result

    async def iterate(query: str, *args: Any, **kwargs: Any):
        state.calls.append((query, args))
        for row in state.rows:
            yield row

    async def execute(query: str, *args: Any, **kwargs: Any):
        state.calls.append((query, args))

    @asynccontextmanager
    async def transaction():
        yield

    monkeypatch.setattr(Postgres, "fetchrow", fetchrow)
    monkeypatch.setattr(Postgres, "iterate", iterate)
    monkeypatch.setattr(Postgres, "execute", execute)
    monkeypatch.setattr(Postgres, "transaction", transaction)
    user = SimpleNamespace(name="alice")
    monkeypatch.setattr(
        documents_module,
        "get_request_context",
        lambda: SimpleNamespace(user=user),
    )
    return state


def test_save_generates_id_and_uses_user(db):
    db.result = {"id": "x"}
    doc_id = asyncio.run(Documents.save("proj", KIND, label="Chart", payload={"a": 1}))
    assert len(doc_id) == 32
    query, args = db.calls[0]
    assert "project_proj.documents" in query
    assert args == (doc_id, KIND, "Chart", {}, {"a": 1}, {}, "alice")


def test_save_keeps_given_id(db):
    db.result = {"id": "x"}
    doc_id = asyncio.run(Documents.save("proj", KIND, document_id=DOC_ID.upper()))
    assert doc_id == DOC_ID


def test_save_conflict_on_other_kind(db):
    db.result = None
    with pytest.raises(ConflictException):
        asyncio.run(Documents.save("proj", KIND, document_id=DOC_ID))


@pytest.mark.parametrize("kind", ["", ".bad", "bad.", "has space", "ok\n", "a/b"])
def test_save_rejects_invalid_kind(db, kind):
    with pytest.raises(BadRequestException):
        asyncio.run(Documents.save("proj", kind))
    assert db.calls == []


def test_save_rejects_invalid_id(db):
    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(Documents.save("proj", KIND, document_id="nope"))
    assert db.calls == []


def test_get(db):
    db.result = _row(payload={"a": 1})
    record = asyncio.run(Documents.get("proj", DOC_ID))
    assert isinstance(record, DocumentRecord)
    assert record.id == DOC_ID
    assert record.payload == {"a": 1}


def test_get_not_found(db):
    with pytest.raises(NotFoundException):
        asyncio.run(Documents.get("proj", DOC_ID))


def test_update_passes_only_given_values(db):
    db.result = _row(data={"icon": "chart"}, access={"private": True})
    asyncio.run(Documents.update("proj", DOC_ID, payload={"a": 1}))
    assert "FOR UPDATE" in db.calls[0][0]
    _, args = db.calls[1]
    assert args == (
        DOC_ID,
        None,
        {"icon": "chart"},
        {"a": 1},
        {"private": True},
        "alice",
    )


@pytest.mark.parametrize("project_name", ["proj", None])
def test_update_removes_null_keys(db, project_name):
    db.result = _row(
        data={"icon": "chart", "color": "red"},
        payload={"keep": 1, "remove": 2, "nested": {"old": True}},
        access={"users": ["alice"], "private": True},
    )
    asyncio.run(
        Documents.update(
            project_name,
            DOC_ID,
            data={"color": None, "missing": None, "count": 0},
            payload={"remove": None, "nested": {"new": None}},
            access={"users": None, "private": False},
        )
    )
    query, args = db.calls[1]
    table = "project_proj.documents" if project_name else "public.documents"
    assert table in query
    assert args == (
        DOC_ID,
        None,
        {"icon": "chart", "count": 0},
        {"keep": 1, "nested": {"new": None}},
        {"private": False},
        "alice",
    )
    assert db.result["data"] == {"icon": "chart", "color": "red"}


def test_update_not_found(db):
    with pytest.raises(NotFoundException):
        asyncio.run(Documents.update("proj", DOC_ID, label="x"))
    assert len(db.calls) == 1


def test_delete(db):
    db.result = {"id": DOC_ID}
    asyncio.run(Documents.delete("proj", DOC_ID))
    assert db.calls[0][1] == (DOC_ID,)


def test_delete_not_found(db):
    with pytest.raises(NotFoundException):
        asyncio.run(Documents.delete("proj", DOC_ID))


async def _collect(**kwargs: Any) -> list[DocumentRecord]:
    return [r async for r in Documents.list("proj", **kwargs)]


def test_list_without_filters(db):
    db.rows = [_row(), _row(id="f" * 32)]
    records = asyncio.run(_collect())
    assert [r.id for r in records] == [DOC_ID, "f" * 32]
    query, args = db.calls[0]
    assert "WHERE" not in query
    assert args == ()


def test_list_filters(db):
    asyncio.run(_collect(kind=KIND, data={"icon": "x"}, payload={"a": 1}))
    query, args = db.calls[0]
    assert "kind = $1" in query
    assert "data @> $2::JSONB" in query
    assert "payload @> $3::JSONB" in query
    assert args == (KIND, {"icon": "x"}, {"a": 1})


def test_list_without_payload(db):
    db.rows = [_row()]
    asyncio.run(_collect(with_payload=False))
    select = db.calls[0][0].split("FROM")[0]
    assert "payload" not in select


@pytest.mark.parametrize("project_name", ["proj", None])
def test_list_by_ids(db, project_name):
    other_id = "f" * 32
    db.rows = [_row(), _row(id=other_id)]

    async def collect():
        return [
            r
            async for r in Documents.list(project_name, ids=[DOC_ID.upper(), other_id])
        ]

    records = asyncio.run(collect())
    assert [r.id for r in records] == [DOC_ID, other_id]
    query, args = db.calls[0]
    table = "project_proj.documents" if project_name else "public.documents"
    assert table in query
    assert "id = ANY($1::uuid[])" in query
    assert args == ([DOC_ID, other_id],)
    assert len(db.calls) == 1


def test_list_by_ids_combines_filters(db):
    asyncio.run(_collect(ids=[DOC_ID], kind=KIND, data={"icon": "x"}, payload={"a": 1}))
    query, args = db.calls[0]
    assert (
        "kind = $1 AND id = ANY($2::uuid[]) "
        "AND data @> $3::JSONB AND payload @> $4::JSONB"
    ) in query
    assert args == (KIND, [DOC_ID], {"icon": "x"}, {"a": 1})


def test_list_by_empty_ids(db):
    assert asyncio.run(_collect(ids=[])) == []
    query, args = db.calls[0]
    assert "id = ANY($1::uuid[])" in query
    assert args == ([],)


def test_list_rejects_invalid_ids(db):
    with pytest.raises(ValueError, match="Invalid entity ID"):
        asyncio.run(_collect(ids=[DOC_ID, "invalid"]))
    assert db.calls == []


@pytest.mark.parametrize("project_name", ["proj", None])
def test_list_query_filter(db, project_name):
    query_filter = QueryFilter(
        conditions=[
            QueryCondition(key="payload/settings/count", operator="gte", value=3),
            QueryFilter(
                operator="or",
                conditions=[
                    QueryCondition(key="label", operator="like", value="chart"),
                    QueryCondition(key="data.icon", value="O'Reilly"),
                ],
            ),
            QueryCondition(key="access.private", value=True),
        ]
    )
    db.rows = [_row()]

    async def collect():
        return [
            row
            async for row in Documents.list(
                project_name,
                kind=KIND,
                ids=[DOC_ID],
                data={"icon": "x"},
                payload={"a": 1},
                filter=query_filter,
                with_payload=False,
            )
        ]

    assert len(asyncio.run(collect())) == 1
    query, args = db.calls[0]
    table = "project_proj.documents" if project_name else "public.documents"
    assert table in query
    assert (
        "kind = $1 AND id = ANY($2::uuid[]) "
        "AND data @> $3::JSONB AND payload @> $4::JSONB AND ("
    ) in query
    assert "payload->'settings'->'count' >= '3'::jsonb" in query
    assert "((label) ILIKE '%chart%' OR data->'icon' = '\"O''Reilly\"'::jsonb)" in query
    assert "coalesce(access->'private', 'false'::jsonb)::boolean" in query
    assert "payload" not in query.split("FROM")[0]
    assert args == (KIND, [DOC_ID], {"icon": "x"}, {"a": 1})


def test_list_empty_query_filter(db):
    asyncio.run(_collect(filter=QueryFilter()))
    assert "WHERE" not in db.calls[0][0]
    assert db.calls[0][1] == ()


@pytest.mark.parametrize(
    "key", ["unknown", "unknown.key", "payload.bad-key", "label.key"]
)
def test_list_rejects_invalid_query_filter(db, key):
    query_filter = QueryFilter(conditions=[QueryCondition(key=key, value="x")])
    with pytest.raises(ValueError):
        asyncio.run(_collect(filter=query_filter))
    assert db.calls == []

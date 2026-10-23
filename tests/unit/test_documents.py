"""Unit tests of the Documents helper with a mocked database."""

import asyncio
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

    monkeypatch.setattr(Postgres, "fetchrow", fetchrow)
    monkeypatch.setattr(Postgres, "iterate", iterate)
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
    db.result = {"id": DOC_ID}
    asyncio.run(Documents.update("proj", DOC_ID, payload={"a": 1}))
    _, args = db.calls[0]
    assert args == (DOC_ID, None, None, {"a": 1}, None, "alice")


def test_update_not_found(db):
    with pytest.raises(NotFoundException):
        asyncio.run(Documents.update("proj", DOC_ID, label="x"))


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

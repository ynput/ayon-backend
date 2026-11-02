"""JSON documents for addons (project or studio scope)

Documents are generic JSON records (configurations, dashboards, markdown
content...) stored in the `documents` table of the project schema or public schema.

- `kind` is a namespaced identifier set by the addon (e.g. `io.ynput.reports.chart`).
  The owner of the kind is responsible for the data model migrations
  (e.g. by storing `data["model_version"]`).
- `data` holds top-level display metadata (icon, color...).
- `payload` holds the main JSON content of the document.
- `access` holds the access control object used for permission evaluation.
"""

import re
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from ayon_server.api.context import get_request_context
from ayon_server.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from ayon_server.helpers.project_list import normalize_project_name
from ayon_server.lib.postgres import Postgres
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.types import Field, OPModel
from ayon_server.utils import EntityID, dict_patch

# Namespaced identifier, e.g. "io.ynput.reports.chart"
DOCUMENT_KIND_REGEX = r"^[a-zA-Z0-9_]([a-zA-Z0-9_\.\-]{0,126}[a-zA-Z0-9_])?$"


class DocumentRecord(OPModel):
    id: str = Field(..., title="Document ID", description="32 hex characters (UUID)")
    kind: str = Field(..., title="Document kind")
    label: str = Field("", title="Document label")
    data: dict[str, Any] = Field(default_factory=dict, title="Display metadata")
    payload: dict[str, Any] = Field(default_factory=dict, title="Document payload")
    access: dict[str, Any] = Field(default_factory=dict, title="Access control")
    created_at: datetime = Field(..., title="Created at")
    updated_at: datetime = Field(..., title="Updated at")
    created_by: str | None = Field(None, title="Created by")
    updated_by: str | None = Field(None, title="Updated by")


def _validate_kind(kind: str) -> None:
    # fullmatch: re.match with "$" would accept a trailing newline
    if not re.fullmatch(DOCUMENT_KIND_REGEX, kind):
        raise BadRequestException(f"Invalid document kind: {kind!r}")


def _table(project_name: str | None) -> str:
    """Project schema table, or the studio-wide one if no project is given"""
    return f"project_{project_name}.documents" if project_name else "public.documents"


def _get_user_name() -> str | None:
    user = get_request_context().user
    return user.name if user else None


class Documents:
    """CRUD helpers for the project `documents` table"""

    @classmethod
    async def save(
        cls,
        project_name: str | None,
        kind: str,
        *,
        document_id: str | None = None,
        label: str = "",
        data: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        access: dict[str, Any] | None = None,
    ) -> str:
        """Create a document or fully overwrite an existing one.

        Raises `ConflictException` if the id belongs to a document
        of another kind. Returns the document id.
        """
        _validate_kind(kind)
        document_id = (
            EntityID.create() if document_id is None else EntityID.parse(document_id)
        )
        user_name = _get_user_name()
        if project_name is not None:
            project_name = await normalize_project_name(project_name)

        res = await Postgres.fetchrow(
            f"""
            INSERT INTO {_table(project_name)}
            (id, kind, label, data, payload, access, created_by, updated_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
            ON CONFLICT (id) DO UPDATE
            SET
                label = EXCLUDED.label,
                data = EXCLUDED.data,
                payload = EXCLUDED.payload,
                access = EXCLUDED.access,
                updated_at = NOW(),
                updated_by = EXCLUDED.updated_by
            WHERE documents.kind = EXCLUDED.kind
            RETURNING id
            """,
            document_id,
            kind,
            label,
            data or {},
            payload or {},
            access or {},
            user_name,
        )
        if res is None:
            raise ConflictException(f"Document {document_id} belongs to another kind")
        return document_id

    @classmethod
    async def get(cls, project_name: str | None, document_id: str) -> DocumentRecord:
        """Return the document record."""
        document_id = EntityID.parse(document_id)
        if project_name is not None:
            project_name = await normalize_project_name(project_name)

        res = await Postgres.fetchrow(
            f"SELECT * FROM {_table(project_name)} WHERE id = $1",
            document_id,
        )
        if res is None:
            raise NotFoundException(f"Document {document_id} not found")
        return DocumentRecord(**res)

    @classmethod
    async def update(
        cls,
        project_name: str | None,
        document_id: str,
        *,
        label: str | None = None,
        data: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        access: dict[str, Any] | None = None,
    ) -> None:
        """Selectively patch a document.

        `label` is replaced. Keys of `data`, `payload` and `access`
        are shallow-merged into the existing values; keys set to None are removed.
        Omitted (None) arguments are left untouched.
        """
        document_id = EntityID.parse(document_id)
        if project_name is not None:
            project_name = await normalize_project_name(project_name)
        async with Postgres.transaction():
            res = await Postgres.fetchrow(
                f"""
                SELECT data, payload, access FROM {_table(project_name)}
                WHERE id = $1 FOR UPDATE
                """,
                document_id,
            )
            if res is None:
                raise NotFoundException(f"Document {document_id} not found")
            await Postgres.execute(
                f"""
                UPDATE {_table(project_name)}
                SET
                    label = COALESCE($2, label),
                    data = $3,
                    payload = $4,
                    access = $5,
                    updated_at = NOW(),
                    updated_by = $6
                WHERE id = $1
                """,
                document_id,
                label,
                dict_patch(res["data"], data or {}),
                dict_patch(res["payload"], payload or {}),
                dict_patch(res["access"], access or {}),
                _get_user_name(),
            )

    @classmethod
    async def delete(cls, project_name: str | None, document_id: str) -> None:
        """Remove the document."""
        document_id = EntityID.parse(document_id)
        if project_name is not None:
            project_name = await normalize_project_name(project_name)
        res = await Postgres.fetchrow(
            f"""
            DELETE FROM {_table(project_name)} WHERE id = $1
            RETURNING id
            """,
            document_id,
        )
        if res is None:
            raise NotFoundException(f"Document {document_id} not found")

    @classmethod
    async def list(
        cls,
        project_name: str | None,
        kind: str | None = None,
        *,
        ids: list[str] | None = None,
        data: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        with_payload: bool = True,
        filter: QueryFilter | None = None,
    ) -> AsyncGenerator[DocumentRecord]:
        """Yield documents, oldest first.

        Optionally filtered by document IDs, kind and by containment: only
        documents whose `data` / `payload` contain all the given key-value pairs
        are returned.
        An empty `ids` list matches no documents; None does not filter by ID.
        `filter` supports QueryFilter conditions on document fields, including
        nested `data`, `payload` and `access` keys. It is ANDed with the other
        filters. Invalid filter fields or paths raise ValueError.
        Use `with_payload=False` to skip the (possibly large) payload.
        """
        conditions = []
        args: list[Any] = []
        if kind is not None:
            args.append(kind)
            conditions.append(f"kind = ${len(args)}")
        if ids is not None:
            args.append([EntityID.parse(document_id) for document_id in ids])
            conditions.append(f"id = ANY(${len(args)}::uuid[])")
        if data:
            args.append(data)
            conditions.append(f"data @> ${len(args)}::JSONB")
        if payload:
            args.append(payload)
            conditions.append(f"payload @> ${len(args)}::JSONB")
        if condition := build_filter(
            filter,
            column_whitelist=list(DocumentRecord.model_fields),
            json_fields=["data", "payload", "access"],
        ):
            conditions.append(condition)

        cols = [
            "id",
            "kind",
            "label",
            "data",
            "access",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        if with_payload:
            cols.append("payload")

        if project_name is not None:
            project_name = await normalize_project_name(project_name)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT {", ".join(cols)}
            FROM {_table(project_name)}
            {where}
            ORDER BY created_at, id
        """
        async for row in Postgres.iterate(query, *args):
            yield DocumentRecord(**row)

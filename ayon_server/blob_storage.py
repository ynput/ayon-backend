"""Project-scoped binary storage for addons

Blobs are arbitrary binary payloads with free-form JSON metadata.
Payloads are stored in the project storage under `blobs/{kind}/{id}`,
metadata in the `blobs` table of the project schema.
"""

import re
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime
from typing import Any

from ayon_server.api.context import get_request_context
from ayon_server.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from ayon_server.files import Storages
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import NAME_REGEX, Field, OPModel
from ayon_server.utils import create_uuid


class BlobRecord(OPModel):
    id: str = Field(..., title="Blob ID")
    kind: str = Field(..., title="Blob kind")
    size: int = Field(..., title="Payload size in bytes")
    data: dict[str, Any] = Field(default_factory=dict, title="Blob metadata")
    created_at: datetime = Field(..., title="Created at")
    updated_at: datetime = Field(..., title="Updated at")
    created_by: str | None = Field(None, title="Created by")
    updated_by: str | None = Field(None, title="Updated by")


def _validate_key(value: str, name: str) -> None:
    if not re.match(NAME_REGEX, value):
        raise BadRequestException(f"Invalid blob {name}: {value}")


def _get_user_name() -> str | None:
    user = get_request_context().user
    return user.name if user else None


class BlobStorage:
    """Store binary payloads with JSON metadata in the project storage

    `kind` is set by the addon and categorizes its blobs
    (for example, the addon name). The blob id alone identifies
    a blob within a project.
    """

    @classmethod
    async def save(
        cls,
        project_name: str,
        kind: str,
        payload: bytes | AsyncIterator[bytes],
        *,
        blob_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> str:
        """Store the payload and create/update the blob record.

        Saving with an existing id overwrites the payload, metadata and size.
        Raises `ConflictException` if the id belongs to a blob of another kind.
        Returns the blob id.
        """
        _validate_key(kind, "kind")
        if blob_id is None:
            blob_id = create_uuid()
        else:
            _validate_key(blob_id, "id")

        existing = await Postgres.fetchrow(
            f"SELECT kind FROM project_{project_name}.blobs WHERE id = $1",
            blob_id,
        )
        if existing and existing["kind"] != kind:
            raise ConflictException(f"Blob {blob_id} belongs to another kind")

        # Payload path contains the kind, so a conflicting save
        # never overwrites a payload of another kind
        storage = await Storages.project(project_name)
        size = await storage.store_blob(kind, blob_id, payload)

        user_name = _get_user_name()
        try:
            res = await Postgres.fetchrow(
                f"""
                INSERT INTO project_{project_name}.blobs
                (id, kind, size, data, created_by, updated_by)
                VALUES ($1, $2, $3, $4, $5, $5)
                ON CONFLICT (id) DO UPDATE
                SET
                    size = EXCLUDED.size,
                    data = EXCLUDED.data,
                    updated_at = NOW(),
                    updated_by = EXCLUDED.updated_by
                WHERE blobs.kind = EXCLUDED.kind
                RETURNING id
                """,
                blob_id,
                kind,
                size,
                data or {},
                user_name,
            )
        except Exception:
            # Keep the payload of an existing record, as it may still be
            # referenced. Only clean up payloads of new blobs.
            if not existing:
                await storage.delete_blob(kind, blob_id)
            raise

        if res is None:
            # The id was taken by another kind in the meantime
            await storage.delete_blob(kind, blob_id)
            raise ConflictException(f"Blob {blob_id} belongs to another kind")

        return blob_id

    @classmethod
    async def get(cls, project_name: str, blob_id: str) -> BlobRecord:
        """Return the blob record (metadata only)."""
        res = await Postgres.fetchrow(
            f"SELECT * FROM project_{project_name}.blobs WHERE id = $1",
            blob_id,
        )
        if res is None:
            raise NotFoundException(f"Blob {blob_id} not found")
        return BlobRecord(**res)

    @classmethod
    async def get_payload(cls, project_name: str, blob_id: str) -> bytes:
        """Return the whole payload as bytes."""
        record = await cls.get(project_name, blob_id)
        storage = await Storages.project(project_name)
        try:
            return await storage.get_blob(record.kind, blob_id)
        except FileNotFoundError:
            raise NotFoundException(f"Blob {blob_id} payload not found") from None

    @classmethod
    async def stream_payload(
        cls,
        project_name: str,
        blob_id: str,
    ) -> AsyncGenerator[bytes]:
        """Return the payload as a stream of chunks."""
        record = await cls.get(project_name, blob_id)
        storage = await Storages.project(project_name)
        try:
            async for chunk in storage.stream_blob(record.kind, blob_id):
                yield chunk
        except FileNotFoundError:
            raise NotFoundException(f"Blob {blob_id} payload not found") from None

    @classmethod
    async def update(
        cls,
        project_name: str,
        blob_id: str,
        data: dict[str, Any],
    ) -> None:
        """Selectively patch the blob metadata. The payload is not touched.

        Provided keys are shallow-merged into the existing metadata.
        """
        res = await Postgres.fetchrow(
            f"""
            UPDATE project_{project_name}.blobs
            SET
                data = data || $2::JSONB,
                updated_at = NOW(),
                updated_by = $3
            WHERE id = $1
            RETURNING id
            """,
            blob_id,
            data,
            _get_user_name(),
        )
        if res is None:
            raise NotFoundException(f"Blob {blob_id} not found")

    @classmethod
    async def delete(cls, project_name: str, blob_id: str) -> None:
        """Remove the blob record and its payload."""
        res = await Postgres.fetchrow(
            f"DELETE FROM project_{project_name}.blobs WHERE id = $1 RETURNING kind",
            blob_id,
        )
        if res is None:
            raise NotFoundException(f"Blob {blob_id} not found")

        storage = await Storages.project(project_name)
        if not await storage.delete_blob(res["kind"], blob_id):
            logger.warning(f"Failed to delete payload of blob {blob_id}")

import os
from typing import Any, Literal

import aiocache
from fastapi import Request
from nxtools import logging

from ayon_server.api.files import handle_upload
from ayon_server.config import ayonconfig
from ayon_server.files.s3 import (
    S3Config,
    delete_s3_file,
    get_signed_url,
    handle_s3_upload,
)
from ayon_server.helpers.cloud import get_instance_id
from ayon_server.helpers.ffprobe import extract_media_info
from ayon_server.lib.postgres import Postgres

StorageType = Literal["local", "s3"]


class ProjectStorage:
    storage_type: StorageType = "local"
    root: str
    bucket_name: str | None = None
    cdn_resolver: str | None = None
    _s3_client: Any = None

    def __init__(
        self,
        project_name: str,
        storage_type: StorageType,
        root: str,
        bucket_name: str | None = None,
        cdn_resolver: str | None = None,
        s3_config: S3Config | None = None,
    ):
        self.project_name = project_name
        self.storage_type = storage_type
        self.root = root
        if storage_type == "s3":
            if not bucket_name:
                raise Exception("Bucket name is required")

            self.bucket_name = bucket_name
            self.s3_config = s3_config or S3Config()
        self.cdn_resolver_url = cdn_resolver

    @classmethod
    def default(cls, project_name: str) -> "ProjectStorage":
        if ayonconfig.default_project_storage_type == "local":
            return cls(
                project_name,
                "local",
                ayonconfig.default_project_storage_root,
                cdn_resolver=ayonconfig.default_project_storage_cdn_resolver,
            )
        elif ayonconfig.default_project_storage_type == "s3":
            return cls(
                project_name,
                "s3",
                ayonconfig.default_project_storage_root,
                bucket_name=ayonconfig.default_project_storage_bucket_name,
                cdn_resolver=ayonconfig.default_project_storage_cdn_resolver,
            )

        raise Exception("Unknown storage type. This should not happen.")

    @aiocache.cached()
    async def get_root(self) -> str:
        instance_id = await get_instance_id()
        return self.root.format(instance_id=instance_id)

    async def get_path(self, file_id: str) -> str:
        root = await self.get_root()
        _file_id = file_id.replace("-", "")
        if len(_file_id) != 32:
            raise ValueError(f"Invalid file ID: {file_id}")
        fgroup = _file_id[:2]
        return os.path.join(
            root,
            self.project_name,
            "uploads",
            fgroup,
            _file_id,
        )

    async def get_signed_url(self, file_id: str, ttl: int = 3600) -> str:
        """Return a signed URL for the file

        This is only supported for S3 storages
        """
        if self.storage_type == "s3":
            path = await self.get_path(file_id)
            assert self.bucket_name  # mypy
            return await get_signed_url(self, path, ttl)
        raise Exception("Signed URLs are only supported for S3 storage")

    async def handle_upload(self, request: Request, file_id: str) -> int:
        """Handle file upload request

        Takes an incoming FastAPI request and saves the file to the
        project storage. Returns the number of bytes written.
        """
        path = await self.get_path(file_id)
        if self.storage_type == "local":
            return await handle_upload(request, path)
        elif self.storage_type == "s3":
            return await handle_s3_upload(self, request, path)
        raise Exception("Unknown storage type")

    async def unlink(self, file_id: str) -> bool:
        """Delete file from the storage if exists

        Database is not affected. Should be used for temporary files,
        (files that weren't stored to the DB yet), or for cleaning up
        files with missing DB records.
        """
        logging.debug("Unlinking file", file_id)

        path = await self.get_path(file_id)
        if self.storage_type == "local":
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except Exception as e:
                logging.error(f"Failed to delete file: {e}")
                return False
            else:
                directory = os.path.dirname(path)
                if os.path.exists(directory):
                    try:
                        os.rmdir(directory)
                    except Exception as e:
                        logging.error(f"Failed to delete directory: {e}")
            return True

        if self.storage_type == "s3":
            assert self.bucket_name  # mypy
            try:
                await delete_s3_file(self, path)
            except Exception as e:
                logging.error(f"Failed to delete file: {e}")
                return False

        raise Exception("Unknown storage type")

    async def delete_file(self, file_id: str) -> None:
        """Delete file from the storage and database"""

        if not await self.unlink(file_id):
            raise Exception("Failed to delete file")

        query = f"""
            DELETE FROM project_{self.project_name}.files
            WHERE id = $1
        """
        await Postgres.execute(query, file_id)
        query = f"""
            WITH updated_activities AS (
                SELECT
                    id,
                    jsonb_set(
                        data,
                        '{{files}}',
                        (SELECT jsonb_agg(elem)
                             FROM jsonb_array_elements(data->'files') elem
                             WHERE elem->>'id' != '{file_id}')
                    ) AS new_data
                FROM
                    project_{self.project_name}.activities
                WHERE
                    data->'files' @> jsonb_build_array(
                        jsonb_build_object('id', '{file_id}')
                    )
            )
            UPDATE project_{self.project_name}.activities
            SET data = updated_activities.new_data
            FROM updated_activities
            WHERE activities.id = updated_activities.id;
        """

        await Postgres.execute(query)

        # prevent circular import
        from ayon_server.helpers.preview import uncache_file_preview

        await uncache_file_preview(self.project_name, file_id)

    async def delete_unused_files(self) -> None:
        """Delete files that are not referenced in any activity."""

        query = f"""
            SELECT id FROM project_{self.project_name}.files
            WHERE activity_id IS NULL
            AND updated_at < NOW() - INTERVAL '5 minutes'
        """

        async for row in Postgres.iterate(query):
            logging.debug(f"Deleting unused file {row['id']}")
            try:
                await self.delete_file(row["id"])
            except Exception:
                pass

    async def extract_media_info(self, file_id: str) -> dict[str, Any]:
        """Extract media info from the file

        Returns a dictionary with media information.
        """
        if self.storage_type == "local":
            path = await self.get_path(file_id)
        elif self.storage_type == "s3":
            path = await self.get_signed_url(file_id)
        return await extract_media_info(path)

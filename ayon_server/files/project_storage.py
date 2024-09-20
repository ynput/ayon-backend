import os
from typing import Literal

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

StorageType = Literal["local", "s3"]


class ProjectStorage:
    storage_type: StorageType = "local"
    root: str
    bucket_name: str | None = None

    def __init__(
        self,
        project_name: str,
        storage_type: StorageType,
        root: str,
        s3_config: S3Config | None = None,
        bucket_name: str | None = None,
    ):
        self.project_name = project_name
        self.storage_type = storage_type
        self.root = root
        if storage_type == "s3":
            if not s3_config:
                raise Exception("S3 configuration is required")
            if not bucket_name:
                raise Exception("Bucket name is required")

            self.bucket_name = bucket_name
            self.s3_config = s3_config

    @classmethod
    def default(cls, project_name: str) -> "ProjectStorage":
        return cls(project_name, "local", ayonconfig.project_data_dir)

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
            return await get_signed_url(self.s3_config, self.bucket_name, path, ttl)
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
            return await handle_s3_upload(
                request, self.s3_config, self.bucket_name, path
            )
        raise Exception("Unknown storage type")

    async def unlink(self, file_id: str) -> None:
        """Delete file from the storage if exists

        Database is not affected. Should be used for temporary files,
        (files that weren't stored to the DB yet), or for cleaning up
        files with missing DB records.
        """

        path = await self.get_path(file_id)
        if self.storage_type == "local":
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except Exception as e:
                logging.error(f"Failed to delete file: {e}")
            return

        if self.storage_type == "s3":
            return await delete_s3_file(self.s3_config, self.bucket_name, path)

        raise Exception("Unknown storage type")

    async def delete(self, file_id: str) -> None:
        """Delete file from the storage and database"""

        pass

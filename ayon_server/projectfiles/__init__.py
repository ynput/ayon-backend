import os
from typing import Literal

import aiocache

from ayon_server.config import ayonconfig
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
        bucket_name: str | None = None,
    ):
        self.project_name = project_name
        self.storage_type = storage_type
        self.root = root
        if storage_type == "s3":
            self.bucket_name = bucket_name

    @classmethod
    def default(cls, project_name: str) -> "ProjectStorage":
        return cls(project_name, "local", ayonconfig.project_data_dir)

    @aiocache.cached()
    async def get_root(self) -> str:
        instance_id = await get_instance_id()
        return self.root.format(instance_id=instance_id)

    async def path(self, file_id: str) -> str:
        root = await self.get_root()
        file_id = file_id.replace("-", "")
        assert len(file_id) == 32
        fgroup = file_id[:2]
        return os.path.join(
            root,
            self.project_name,
            "uploads",
            fgroup,
            file_id,
        )


# This is for testing purposes

PROJECT_STORAGE_OVERRIDES = {
    "demo_Commercial": ProjectStorage(
        "demo_Commercial",
        "s3",
        "media/{instance_id}/server/projects",
    ),
}


class ProjectFiles:
    @classmethod
    async def __call__(cls, project_name: str) -> ProjectStorage:
        storage = PROJECT_STORAGE_OVERRIDES.get(project_name)
        if storage:
            return storage
        return ProjectStorage.default(project_name)

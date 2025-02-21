__all__ = ["ProjectStorage", "create_project_file_record", "Storages"]

from typing import Any

from ayon_server.files.project_file_record import create_project_file_record
from ayon_server.files.project_storage import ProjectStorage


class Storages:
    project_storage_overrides: dict[str, Any] = {}

    @classmethod
    async def project(cls, project_name: str) -> ProjectStorage:
        storage = cls.project_storage_overrides.get(project_name)
        if storage:
            return storage
        return ProjectStorage.default(project_name)

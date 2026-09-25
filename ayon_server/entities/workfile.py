import os
from typing import NoReturn

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.types import ProjectLevelEntityType


class WorkfileEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "workfile"
    model = ModelSet("workfile", attribute_library["workfile"])

    async def ensure_create_access(self, user, **kwargs) -> None:
        if user.is_manager:
            return

        await ensure_entity_access(
            user,
            self.project_name,
            "task",
            self.task_id,
            "publish",
        )

    #
    # Properties
    #

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @name.setter
    def name(self, value: str) -> NoReturn:
        raise AttributeError("Cannot set name of a workfile.")

    @property
    def path(self) -> str:
        return self._payload.path  # type: ignore

    @path.setter
    def path(self, value: str) -> None:
        self._payload.path = value  # type: ignore

    @property
    def task_id(self) -> str:
        return self._payload.task_id  # type: ignore

    @task_id.setter
    def task_id(self, value: str) -> None:
        self._payload.task_id = value  # type: ignore

    @property
    def parent_id(self) -> str:
        return self.task_id

    @property
    def thumbnail_id(self) -> str:
        return self._payload.thumbnail_id  # type: ignore

    @thumbnail_id.setter
    def thumbnail_id(self, value: str) -> None:
        self._payload.thumbnail_id = value  # type: ignore

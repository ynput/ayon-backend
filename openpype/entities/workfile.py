import os
from typing import NoReturn

from openpype.entities.core import ProjectLevelEntity, attribute_library
from openpype.entities.models import ModelSet
from openpype.types import ProjectLevelEntityType


class WorkfileEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "workfile"
    model = ModelSet("task", attribute_library["workfile"])

    #
    # Properties
    #

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @name.setter
    def name(self, value) -> NoReturn:
        raise AttributeError("Cannot set name of a workfile.")

    @property
    def path(self) -> str:
        return self._payload.path

    @path.setter
    def path(self, value) -> None:
        self._payload.path = value

    @property
    def task_id(self) -> str:
        return self._payload.task_id

    @task_id.setter
    def task_id(self, value: str) -> None:
        self._payload.task_id = value

    @property
    def thumbnail_id(self) -> str:
        return self._payload.thumbnail_id

    @thumbnail_id.setter
    def thumbnail_id(self, value: str) -> None:
        self._payload.thumbnail_id = value

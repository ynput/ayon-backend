from openpype.entities.core import ProjectLevelEntity, attribute_library
from openpype.entities.models import ModelSet
from openpype.types import ProjectLevelEntityType


class TaskEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "task"
    model = ModelSet("task", attribute_library["task"])

    #
    # Properties
    #

    @property
    def folder_id(self) -> str:
        return self._payload.folder_id

    @folder_id.setter
    def folder_id(self, value: str) -> None:
        self._payload.folder_id = value

    @property
    def task_type(self) -> str:
        return self._payload.task_type

    @task_type.setter
    def task_type(self, value: str) -> None:
        self._payload.task_type = value

    @property
    def assignees(self) -> list:
        return self._payload.assignees

    @assignees.setter
    def assignees(self, value: list) -> None:
        self._payload.assignees = value

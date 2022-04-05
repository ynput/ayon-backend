from openpype.entities.core import ProjectLevelEntity, attribute_library
from openpype.entities.models import ModelSet


class TaskEntity(ProjectLevelEntity):
    entity_type: str = "task"
    model = ModelSet("task", attribute_library["task"])

    #
    # Properties
    #

    @property
    def name(self) -> str:
        return self._payload.name

    @name.setter
    def name(self, value: str):
        self._payload.name = value

    @property
    def folder_id(self) -> str:
        return self._payload.folder_id

    @folder_id.setter
    def folder_id(self, value: str):
        self._payload.folder_id = value

    @property
    def task_type(self) -> str:
        return self._payload.task_type

    @task_type.setter
    def task_type(self, value: str):
        self._payload.task_type = value

    @property
    def assignees(self) -> list:
        return self._payload.assignees

    @assignees.setter
    def assignees(self, value: list):
        self._payload.assignees = value

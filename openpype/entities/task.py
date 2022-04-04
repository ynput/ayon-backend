from openpype.entities.core import ProjectLevelEntity, attribute_library
from openpype.entities.models import ModelSet


class TaskEntity(ProjectLevelEntity):
    entity_type: str = "task"
    model = ModelSet("task", attribute_library["task"])

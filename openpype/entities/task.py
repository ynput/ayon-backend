from .common import Entity, EntityType, attribute_library
from .models import ModelSet


class TaskEntity(Entity):
    entity_type = EntityType.TASK
    entity_name = "task"
    model = ModelSet("task", attribute_library["task"])

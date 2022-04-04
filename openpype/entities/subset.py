from openpype.entities.core import ProjectLevelEntity, attribute_library
from openpype.entities.models import ModelSet


class SubsetEntity(ProjectLevelEntity):
    entity_type: str = "subset"
    model = ModelSet("subset", attribute_library["subset"])

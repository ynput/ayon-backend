from openpype.entities.core import ProjectLevelEntity, attribute_library
from openpype.entities.models import ModelSet


class RepresentationEntity(ProjectLevelEntity):
    entity_type: str = "representation"
    model = ModelSet("representation", attribute_library["representation"])

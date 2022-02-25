from .common import Entity, EntityType, attribute_library
from .models import ModelSet


class RepresentationEntity(Entity):
    entity_type = EntityType.REPRESENTATION
    entity_name = "representation"
    model = ModelSet("representation", attribute_library["representation"])

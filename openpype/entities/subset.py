from .common import Entity, EntityType, attribute_library
from .models import ModelSet


class SubsetEntity(Entity):
    entity_type = EntityType.SUBSET
    entity_name = "subset"
    model = ModelSet("subset", attribute_library["subset"])

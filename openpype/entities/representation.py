from openpype.entities.core import ProjectLevelEntity, attribute_library
from openpype.entities.models import ModelSet


class RepresentationEntity(ProjectLevelEntity):
    entity_type: str = "representation"
    model = ModelSet("representation", attribute_library["representation"])

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
    def version_id(self) -> str:
        return self._payload.version_id

    @version_id.setter
    def version_id(self, value: str):
        self._payload.version_id = value

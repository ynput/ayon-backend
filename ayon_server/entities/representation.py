from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.types import ProjectLevelEntityType


class RepresentationEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "representation"
    model = ModelSet("representation", attribute_library["representation"])

    #
    # Properties
    #

    @property
    def version_id(self) -> str:
        return self._payload.version_id

    @version_id.setter
    def version_id(self, value: str):
        self._payload.version_id = value

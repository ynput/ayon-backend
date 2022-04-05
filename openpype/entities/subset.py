from openpype.entities.core import ProjectLevelEntity, attribute_library
from openpype.entities.models import ModelSet


class SubsetEntity(ProjectLevelEntity):
    entity_type: str = "subset"
    model = ModelSet("subset", attribute_library["subset"])

    #
    # Properties
    #

    @property
    def name(self) -> str:
        return self._payload.name

    @name.setter
    def name(self, value: str):
        self.model._payload = value

    @property
    def folder_id(self) -> str:
        return self._payload.folder_id

    @folder_id.setter
    def folder_id(self, value: str):
        self.model._payload = value

    @property
    def family(self) -> str:
        return self._payload.family

    @family.setter
    def family(self, value: str):
        self.model._payload = value

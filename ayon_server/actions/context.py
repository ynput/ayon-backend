from ayon_server.entities import ProjectEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.exceptions import NotFoundException
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.types import Field, OPModel, ProjectLevelEntityType


class ActionContext(OPModel):
    """
    frontend sends this to backend.
    backend asks addons for actions based on this model.
    """

    _project_entity: ProjectEntity | None = None
    _entities: list[ProjectLevelEntity] | None = None

    project_name: str = Field(
        ...,
        description="The name of the project",
        example="my_project",
    )
    entity_type: ProjectLevelEntityType | None = Field(
        ...,
        description="The type of the entity",
        example="folder",
    )

    # frontend already knows this, so it can speed up
    # the action resolving process when it sends this.
    entity_subtypes: list[str] | None = Field(
        None,
        description="List of subtypes present in the entity list",
        example=["asset"],
    )

    entity_ids: list[str] | None = Field(
        ...,
        title="Entity IDs",
        description="The IDs of the entities",
        example=["1a3bfe33-1b1b-4b1b-8b1b-1b1b1b1b1b1b"],
    )

    async def get_entities(self) -> list[ProjectLevelEntity]:
        """Cached entities DURING THE REQUEST"""

        if self.entity_type is None or self.entity_ids is None:
            return []

        if self._entities is None:
            result = []
            entity_class = get_entity_class(self.entity_type)
            for entity_id in self.entity_ids:
                try:
                    entity = await entity_class.load(self.project_name, entity_id)
                except NotFoundException:
                    continue
                result.append(entity)

            self._entities = result
        return self._entities

    async def get_project_entity(self) -> ProjectEntity:
        """Cached project entity DURING THE REQUEST"""

        if self._project_entity is None:
            self._project_entity = await ProjectEntity.load(self.project_name)
        return self._project_entity

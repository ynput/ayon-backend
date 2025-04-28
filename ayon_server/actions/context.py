from typing import Annotated, Any

from pydantic import validator

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

    project_name: Annotated[
        str | None,
        Field(
            title="Project Name",
            description=(
                "The name of the project. "
                "If not provided, use global actions, "
                "the rest of the fields are ignored."
            ),
            example="my_project",
        ),
    ] = None

    entity_type: Annotated[
        ProjectLevelEntityType | None,
        Field(
            title="Entity Type",
            description=(
                "The type of the entity. "
                "If not specified, project-lever "
                "or global actions are used."
            ),
            example="folder",
        ),
    ] = None

    # frontend already knows this, so it can speed up
    # the action resolving process when it sends this.

    entity_subtypes: Annotated[
        list[str] | None,
        Field(
            title="Entity Subtypes",
            description="List of subtypes present in the entity list",
            example=["asset"],
        ),
    ] = None

    entity_ids: Annotated[
        list[str] | None,
        Field(
            title="Entity IDs",
            description="The IDs of the entities",
            example=["1a3bfe33-1b1b-4b1b-8b1b-1b1b1b1b1b1b"],
        ),
    ] = None

    form_data: Annotated[
        dict[str, Any] | None,
        Field(
            title="Form Data",
            description="The data from the form",
            example={"key": "value"},
        ),
    ] = None

    #
    # Sanity checks
    #

    @validator("entity_type", "entity_subtypes", "entity_ids")
    def global_actions_only(cls, v, values):
        """
        If project_name is not provided, ignore the rest of the fields.
        """
        if values.get("project_name") is None:
            return None
        return v

    @validator("entity_ids")
    def validate_entity_ids(cls, v, values):
        if values.get("project_name") is None:
            return None
        if values.get("entity_type") is None:
            return None
        if v is None:
            return []
        return v

    #
    # Entity caching
    #

    async def get_entities(self) -> list[ProjectLevelEntity]:
        """Cached entities DURING THE REQUEST"""

        if (
            self.project_name is None
            or self.entity_type is None
            or self.entity_ids is None
        ):
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

    async def get_project_entity(self) -> ProjectEntity | None:
        """Cached project entity DURING THE REQUEST"""

        if not self.project_name:
            return None

        if self._project_entity is None:
            self._project_entity = await ProjectEntity.load(self.project_name)
        return self._project_entity

    #
    # Context comparison
    #

    def __hash__(self):
        elength = len(self.entity_ids) > 1 if self.entity_ids else 0
        hash_base = (
            self.project_name,
            self.entity_type,
            self.entity_subtypes,
            elength,
        )
        return hash(hash_base)

    def __eq__(self, other: Any):
        if isinstance(other, ActionContext):
            return self.__hash__() == other.__hash__()
        return False

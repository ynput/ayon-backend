from ayon_server.types import Field, OPModel, ProjectLevelEntityType


class ActionContextModel(OPModel):
    """
    frontend sends this to backend.
    backend asks addons for actions based on this model.
    """

    project_name: str = Field(
        ...,
        description="The name of the project",
    )
    entity_type: ProjectLevelEntityType | None = Field(
        ...,
        description="The type of the entity",
    )
    entity_ids: list[str] | None = Field(
        ...,
        title="Entity IDs",
    )

    def get_entities(self):
        """Cached entities DURING THE REQUEST"""
        ...

    def get_project_entity(self):
        """Cached project entity DURING THE REQUEST"""
        ...

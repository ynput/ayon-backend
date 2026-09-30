"""Entity models.

Each entity type has three models (see `common` and the entity modules):

- `FolderModel` - the entity
- `FolderPostModel` - a new entity
- `FolderPatchModel` - a partial update of an entity

Attribute values (`attrib`) are validated against the current attribute
definitions (see `attrib`), so the models do not depend on them.
"""

from pydantic import BaseModel

from ayon_server.entities.models.attrib import AttribModelConfig, get_attrib_model

__all__ = ["AttribModelConfig", "ModelSet"]


class ModelSet:
    """Models of an entity type (`Entity.model`)."""

    def __init__(
        self,
        entity_name: str,
        main_model: type[BaseModel],
        post_model: type[BaseModel],
        patch_model: type[BaseModel],
        *,
        dynamic_fields: list[str],
    ) -> None:
        self.entity_name = entity_name
        self.main_model = main_model
        self.post_model = post_model
        self.patch_model = patch_model
        # Fields computed when the entity is loaded, which are not stored
        self.dynamic_fields = [*dynamic_fields, "own_attrib"]

    @property
    def attrib_model(self) -> type[BaseModel]:
        """Attribute model of the entity type (current attribute definitions)."""
        return get_attrib_model(self.entity_name)

"""Entity models.

Each entity type has three models (see `common` and the entity modules):

- `FolderModel` - the entity
- `FolderPostModel` - a new entity
- `FolderPatchModel` - a partial update of an entity

Attribute values (`attrib`) are validated against the current attribute
definitions (see `attrib`), so the models do not depend on them.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

from ayon_server.entities.models.attrib import AttribModelConfig, get_attrib_model
from ayon_server.entities.models.common import EntityMainModel, EntityModel

__all__ = ["AttribModelConfig", "ModelSet"]

MainModelT = TypeVar(
    "MainModelT", bound=EntityMainModel, default=EntityMainModel, covariant=True
)
PostModelT = TypeVar(
    "PostModelT", bound=EntityModel, default=EntityModel, covariant=True
)
PatchModelT = TypeVar(
    "PatchModelT", bound=EntityModel, default=EntityModel, covariant=True
)


class ModelSet(Generic[MainModelT, PostModelT, PatchModelT]):
    """Models of an entity type (`Entity.model`)."""

    def __init__(
        self,
        entity_name: str,
        main_model: type[MainModelT],
        post_model: type[PostModelT],
        patch_model: type[PatchModelT],
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

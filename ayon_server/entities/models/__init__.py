"""Dynamic entity models generation."""

import copy
from typing import Any

from pydantic import BaseModel

from ayon_server.entities.models.config import EntityModelConfig
from ayon_server.entities.models.fields import (
    folder_fields,
    product_fields,
    project_fields,
    representation_fields,
    task_fields,
    user_fields,
    version_fields,
    workfile_fields,
)
from ayon_server.entities.models.generator import generate_model
from ayon_server.types import (
    ENTITY_ID_EXAMPLE,
    ENTITY_ID_REGEX,
    NAME_REGEX,
    USER_NAME_REGEX,
)

FIELD_LISTS: dict[str, list[Any]] = {
    "project": project_fields,
    "user": user_fields,
    "folder": folder_fields,
    "task": task_fields,
    "product": product_fields,
    "version": version_fields,
    "representation": representation_fields,
    "workfile": workfile_fields,
}


class AttribModelConfig:
    """Configuration of the attribute model.

    Attributes are immutable - that enforces you to
    use patch method of the entity to change attributes.

    This is used to keep track which attributes are
    own entity attributes and which are inherited).
    """

    _is_attrib_model = True

    # On the other hand, in demogen, we need to be able to
    # set attributes on the fly, so we need to allow it.
    # TODO: How to handle this situation?

    # allow_mutation = False


class ModelSet:
    """Set of models used for each entity type.

    Based on given fields and attibutes, generate the following models:

    - EntityModel
    - EntityPostModel
    - EntityPatchModel
    - EntityAttributeModel

    """

    def __init__(
        self,
        entity_name: str,
        attributes: list[dict[str, Any]] | None = None,
        has_id: bool = True,
    ):
        """Initialize the model set."""
        self.entity_name = entity_name
        self.fields: list[Any] = FIELD_LISTS[entity_name]

        self.attributes = attributes or []
        self.has_id = has_id

        self._model: type[BaseModel] | None = None
        self._post_model: type[BaseModel] | None = None
        self._patch_model: type[BaseModel] | None = None
        self._attrib_model: type[BaseModel] | None = None

    @property
    def attrib_model(self) -> type[BaseModel]:
        """Return the attribute model."""
        if self._attrib_model is None:
            self._attrib_model = generate_model(
                f"{self.entity_name.capitalize()}AttribModel",
                self.attributes,
                AttribModelConfig,
            )
        assert self._attrib_model is not None
        return self._attrib_model

    @property
    def main_model(self) -> type[BaseModel]:
        """Return the entity model."""
        if self._model is None:
            self._model = self._generate_entity_model()
        assert self._model is not None
        return self._model

    @property
    def post_model(self) -> type[BaseModel]:
        """Return the post model."""
        if self._post_model is None:
            self._post_model = self._generate_post_model()
        assert self._post_model is not None
        return self._post_model

    @property
    def patch_model(self) -> type[BaseModel]:
        """Return the patch model."""
        if self._patch_model is None:
            self._patch_model = self._generate_patch_model()
        assert self._patch_model is not None
        return self._patch_model

    #
    # Model generators
    #

    @property
    def dynamic_fields(self) -> list[str]:
        """Return a list of field names, which are dynamic.

        Dynamic fields cannot be used in inserts and updates.
        """
        return [f["name"] for f in self.fields if f.get("dynamic")] + ["own_attrib"]

    @property
    def _common_fields(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "attrib",
                "submodel": self.attrib_model,
                "required": False,
                "title": f"{self.entity_name.capitalize()} attributes",
            },
            {
                "name": "data",
                "type": "dict",
                "factory": "dict",
                "title": f"{self.entity_name.capitalize()} auxiliary data",
            },
            {
                "name": "active",
                "type": "boolean",
                "title": f"{self.entity_name.capitalize()} active",
                "description": f"Whether the {self.entity_name} is active",
                "default": True,
            },
            {
                "name": "own_attrib",
                "type": "list_of_strings",
                "title": "Own attributes",
                "example": ["frameStart", "frameEnd"],
                "dynamic": True,
            },
        ]

    @property
    def _project_level_fields(self) -> list[dict[str, Any]]:
        if self.entity_name in ["project", "user"]:
            return []
        return [
            {
                "name": "status",
                "type": "string",
                "title": f"{self.entity_name.capitalize()} status",
                "description": f"Status of the {self.entity_name}",
                "example": "In progress",
                "required": False,  # It is required in the DB, but not in the model
            },
            {
                "name": "tags",
                "type": "list_of_strings",
                "title": f"{self.entity_name.capitalize()} tags",
                "description": f"Tags assigned to the the {self.entity_name}",
                "factory": "list",
                "example": ["flabadob", "blip", "blop", "blup"],
            },
            {
                "name": "created_by",
                "type": "string",
                "title": "Created by",
                "description": f"Who created the {self.entity_name}",
                "example": "Moe",
                "required": False,
            },
            {
                "name": "updated_by",
                "type": "string",
                "title": "Updated by",
                "description": f"Who last updated the {self.entity_name}",
                "example": "Homer",
                "required": False,
            },
        ]

    def _generate_entity_model(self) -> type[BaseModel]:
        """Generate the entity model."""
        model_name = f"{self.entity_name.capitalize()}Model"
        pre_fields: list[dict[str, Any]] = (
            [
                {
                    "name": "id",
                    "type": "string",
                    "factory": "uuid",
                    "title": f"{self.entity_name.capitalize()} ID",
                    "description": "Unique identifier of the {entity_name}",
                    "example": ENTITY_ID_EXAMPLE,
                    "regex": ENTITY_ID_REGEX,
                }
            ]
            if self.has_id
            else [
                {
                    "name": "name",
                    "type": "string",
                    "required": True,
                    "title": f"{self.entity_name.capitalize()} name",
                    "description": "Name is an unique id of the {entity_name}",
                    "example": f"awesome_{self.entity_name.lower()}",
                    "regex": USER_NAME_REGEX
                    if self.entity_name.lower() == "user"
                    else NAME_REGEX,
                }
            ]
        )

        post_fields: list[dict[str, Any]] = [
            {
                "name": "created_at",
                "type": "datetime",
                "factory": "now",
                "title": "Created at",
                "description": "Time of creation",
                "example": "2023-01-01T00:00:00+00:00",
            },
            {
                "name": "updated_at",
                "type": "datetime",
                "factory": "now",
                "title": "Updated at",
                "description": "Time of last update",
                "example": "2023-01-01T00:00:00+00:00",
            },
        ]

        return generate_model(
            model_name,
            pre_fields
            + self.fields
            + self._common_fields
            + self._project_level_fields
            + post_fields,
            EntityModelConfig,
        )

    def _generate_post_model(self) -> type[BaseModel]:
        """Generate the post model."""
        model_name = f"{self.entity_name.capitalize()}PostModel"
        # Allow setting the ID explicitly
        fields = (
            [
                {
                    "name": "id",
                    "type": "string",
                    "title": "Entity ID",
                    "factory": "uuid",
                    "description": "Explicitly set the ID of the entity",
                    "regex": ENTITY_ID_REGEX,
                    "example": ENTITY_ID_EXAMPLE,
                }
            ]
            if self.has_id
            else []
        )
        for f in self.fields + self._project_level_fields + self._common_fields:
            if f.get("dynamic"):
                continue
            fields.append(f)

        return generate_model(model_name, fields, EntityModelConfig)

    def _generate_patch_model(self) -> type[BaseModel]:
        """Generate the patch model."""
        model_name = f"{self.entity_name.capitalize()}PatchModel"
        fields = []
        for original_field in (
            self.fields + self._project_level_fields + self._common_fields
        ):
            if original_field.get("dynamic"):
                continue
            field = copy.deepcopy(original_field)
            field["required"] = False
            fields.append(field)
        return generate_model(model_name, fields, EntityModelConfig)

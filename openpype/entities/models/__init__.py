"""Dynamic entity models generation."""

import copy
from typing import Any, Type

from pydantic import BaseModel

from openpype.entities.models.config import EntityModelConfig
from openpype.entities.models.fields import (
    folder_fields,
    project_fields,
    representation_fields,
    subset_fields,
    task_fields,
    version_fields,
)
from openpype.entities.models.generator import generate_model
from openpype.types import ENTITY_ID_EXAMPLE, ENTITY_ID_REGEX, NAME_REGEX, USER_NAME_REGEX

FIELD_LISTS: dict[str, list[Any]] = {
    "project": project_fields,
    "user": [],
    "folder": folder_fields,
    "task": task_fields,
    "subset": subset_fields,
    "version": version_fields,
    "representation": representation_fields,
}


class AttribModelConfig:
    """Configuration of the attribute model.

    Attributes are immutable - that enforces you to
    use patch method of the entity to change attributes.

    This is used to keep track which attributes are
    own entity attributes and which are inherited).
    """

    allow_mutation = False


class ModelSet:
    """Set of models used for each entity type.

    Based on given fields and attibutes, generate the following models:

    - EntityModel
    - EntityPostModel
    - EntityPatchModel
    - EntityAttributeModel

    """

    def __init__(self, entity_name: str, attributes: list = None, has_id: bool = True):
        """Initialize the model set."""
        self.entity_name = entity_name
        self.fields: list[Any] = FIELD_LISTS[entity_name]

        self.attributes = attributes if attributes else []
        self.has_id = has_id

        self._model: Type[BaseModel] | None = None
        self._post_model: Type[BaseModel] | None = None
        self._patch_model: Type[BaseModel] | None = None
        self._attrib_model: Type[BaseModel] | None = None

    @property
    def attrib_model(self) -> Type[BaseModel]:
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
    def main_model(self) -> Type[BaseModel]:
        """Return the entity model."""
        if self._model is None:
            self._model = self._generate_entity_model()
        assert self._model is not None
        return self._model

    @property
    def post_model(self) -> Type[BaseModel]:
        """Return the post model."""
        if self._post_model is None:
            self._post_model = self._generate_post_model()
        assert self._post_model is not None
        return self._post_model

    @property
    def patch_model(self) -> Type[BaseModel]:
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
    def _common_fields(self) -> list:
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

    def _generate_entity_model(self) -> Type[BaseModel]:
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
                "type": "integer",
                "factory": "now",
                "title": "Created at",
                "description": "Timestamp of creation",
                "example": 1605849600,
                "gt": 0,
            },
            {
                "name": "updated_at",
                "type": "integer",
                "factory": "now",
                "title": "Updated at",
                "description": "Timestamp of last update",
                "example": 1605849600,
                "gt": 0,
            },
        ]

        return generate_model(
            model_name,
            pre_fields + self.fields + self._common_fields + post_fields,
            EntityModelConfig,
        )

    def _generate_post_model(self) -> Type[BaseModel]:
        """Generate the post model."""
        model_name = f"{self.entity_name.capitalize()}PostModel"
        fields = [f for f in self.fields if not f.get("dynamic")]
        return generate_model(
            model_name, fields + self._common_fields, EntityModelConfig
        )

    def _generate_patch_model(self) -> Type[BaseModel]:
        """Generate the patch model."""
        model_name = f"{self.entity_name.capitalize()}PatchModel"
        fields = []
        for original_field in self.fields:
            if original_field.get("dynamic"):
                continue
            field = copy.deepcopy(original_field)
            field["required"] = False
            fields.append(field)
        return generate_model(
            model_name, fields + self._common_fields, EntityModelConfig
        )

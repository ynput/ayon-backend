"""Dynamic entity models generation."""

import copy

from typing import Literal
from pydantic import BaseModel

from .generator import generate_model
from .config import EntityModelConfig
from .constants import NAME_REGEX, ENTITY_ID_EXAMPLE, ENTITY_ID_REGEX

from .fields import (
    project_fields,
    folder_fields,
    task_fields,
    subset_fields,
    version_fields,
    representation_fields,
)


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
        self.fields = {
            "project": project_fields,
            "user": [],
            "folder": folder_fields,
            "task": task_fields,
            "subset": subset_fields,
            "version": version_fields,
            "representation": representation_fields,
        }[entity_name]

        self.attributes = attributes if attributes else []
        self.has_id = has_id

        self._model = None
        self._post_model = None
        self._patch_model = None
        self._attrib_model = None

    def __call__(self, model_type: Literal["main", "post", "patch", "attrib"] = "main"):
        """Return a model."""
        if model_type == "main":
            return self.main_model
        elif model_type == "post":
            return self.post_model
        elif model_type == "patch":
            return self.patch_model
        elif model_type == "attrib":
            return self.attrib_model

    @property
    def attrib_model(self) -> BaseModel:
        """Return the attribute model."""
        if not self._attrib_model:
            self._attrib_model = generate_model(
                f"{self.entity_name.capitalize()}AttribModel",
                self.attributes,
            )
        return self._attrib_model

    @property
    def main_model(self):
        """Return the entity model."""
        if self._model is None:
            self._model = self._generate_entity_model()
        return self._model

    @property
    def post_model(self) -> BaseModel:
        """Return the post model."""
        if self._post_model is None:
            self._post_model = self._generate_post_model()
        return self._post_model

    @property
    def patch_model(self) -> BaseModel:
        """Return the patch model."""
        if self._patch_model is None:
            self._patch_model = self._generate_patch_model()
        return self._patch_model

    #
    # Model generators
    #

    @property
    def dynamic_fields(self) -> list[str]:
        """Return a list of field names, which are dynamic.

        Dynamic fields cannot be used in inserts and updates.
        """
        return [f["name"] for f in self.fields if f.get("dynamic")]

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
        ]

    def _generate_entity_model(self) -> BaseModel:
        """Generate the entity model."""
        model_name = f"{self.entity_name.capitalize()}Model"
        pre_fields = (
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
                    "regex": NAME_REGEX,
                }
            ]
        )

        post_fields = [
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

    def _generate_post_model(self) -> BaseModel:
        """Generate the post model."""
        model_name = f"{self.entity_name.capitalize()}PostModel"
        fields = [f for f in self.fields if not f.get("dynamic")]
        return generate_model(
            model_name, fields + self._common_fields, EntityModelConfig
        )

    def _generate_patch_model(self) -> BaseModel:
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

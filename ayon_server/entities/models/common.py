"""Base of the entity models and the fields shared by the entities.

Each entity has three models: the entity model (`FolderModel`), the model
of a new entity (`FolderPostModel`) and of a partial update
(`FolderPatchModel`). The models are written out explicitly. Fields shared
by the models (and entities) are defined once, as `Field` objects used in
`Annotated` types, while each model sets its own type and default:

    name: Annotated[str, FOLDER_NAME]                # required
    name: Annotated[str | None, FOLDER_NAME] = None  # optional (patch)
"""

from typing import Any, ClassVar

from pydantic import ValidationInfo, field_validator

from ayon_server.entities.models.attrib import validate_attrib
from ayon_server.models.rest_model import RestModel
from ayon_server.types import ENTITY_ID_EXAMPLE, ENTITY_ID_REGEX, Field


class EntityModel(RestModel):
    """Base of the entity models.

    Attribute values (`attrib`) are validated against the current
    attribute definitions of `entity_type` (see validate_attrib).
    """

    entity_type: ClassVar[str]

    @field_validator("attrib", mode="before", check_fields=False)
    @classmethod
    def validate_attrib_values(cls, value: Any, info: ValidationInfo) -> Any:
        return validate_attrib(cls.entity_type, value, info.context)


#
# Fields of all entities
#

ENTITY_ID = Field(
    title="Entity ID",
    description="Unique identifier of the entity",
    pattern=ENTITY_ID_REGEX,
    example=ENTITY_ID_EXAMPLE,
)

ATTRIB = Field(title="Attributes")

DATA = Field(title="Auxiliary data")

ACTIVE = Field(title="Active", description="Whether the entity is active")

OWN_ATTRIB = Field(
    title="Own attributes",
    description="Attributes set on the entity itself (not inherited)",
    example=["frameStart", "frameEnd"],
)

CREATED_AT = Field(
    title="Created at",
    description="Time of creation",
    example="2023-01-01T00:00:00+00:00",
)

UPDATED_AT = Field(
    title="Updated at",
    description="Time of last update",
    example="2023-01-01T00:00:00+00:00",
)

#
# Fields of project-level entities
#

STATUS = Field(
    title="Status",
    description="Status of the entity",
    example="In progress",
)

TAGS = Field(
    title="Tags",
    description="Tags assigned to the entity",
    example=["flabadob", "blip", "blop", "blup"],
)

CREATED_BY = Field(
    title="Created by",
    description="Who created the entity",
    example="Moe",
)

UPDATED_BY = Field(
    title="Updated by",
    description="Who last updated the entity",
    example="Homer",
)

THUMBNAIL_ID = Field(
    title="Thumbnail ID",
    pattern=ENTITY_ID_REGEX,
    example=ENTITY_ID_EXAMPLE,
)

FOLDER_ID = Field(
    title="Folder ID",
    description="ID of the parent folder",
    pattern=ENTITY_ID_REGEX,
    example=ENTITY_ID_EXAMPLE,
)

TASK_ID = Field(
    title="Task ID",
    description="ID of the parent task",
    pattern=ENTITY_ID_REGEX,
    example=ENTITY_ID_EXAMPLE,
)

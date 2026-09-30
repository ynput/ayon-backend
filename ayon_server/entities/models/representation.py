from datetime import datetime
from typing import Annotated, Any, ClassVar

from ayon_server.entities.models.common import (
    ACTIVE,
    ATTRIB,
    CREATED_AT,
    CREATED_BY,
    DATA,
    ENTITY_ID,
    OWN_ATTRIB,
    STATUS,
    TAGS,
    UPDATED_AT,
    UPDATED_BY,
    EntityModel,
)
from ayon_server.entities.models.submodels import RepresentationFileModel
from ayon_server.models.attrib_values import AttribDict
from ayon_server.types import ENTITY_ID_EXAMPLE, ENTITY_ID_REGEX, NAME_REGEX, Field
from ayon_server.utils import create_uuid

REPRESENTATION_NAME = Field(
    title="Name",
    description="The name of the representation",
    pattern=NAME_REGEX,
    example="ma",
)
VERSION_ID = Field(
    title="Version ID",
    description="ID of the parent version",
    pattern=ENTITY_ID_REGEX,
    example=ENTITY_ID_EXAMPLE,
)
FILES = Field(title="Files", description="List of files")
TRAITS = Field(
    title="Traits",
    description="Dict of traits",
    example={
        "ayon.2d.PixelBased.v1": {
            "display_window_width": 1920,
            "display_window_height": 1080,
        },
        "ayon.2d.Image.v1": {},
    },
)
REPRESENTATION_PATH = Field(
    title="Path",
    example="/assets/characters/xenomorph/modelMain/v003/ma",
)
BELONGS_TO_HERO = Field(title="Belongs to HERO version", example=False)


class RepresentationModel(EntityModel):
    entity_type: ClassVar[str] = "representation"

    id: Annotated[str | None, ENTITY_ID] = Field(default_factory=create_uuid)
    name: Annotated[str, REPRESENTATION_NAME]
    version_id: Annotated[str, VERSION_ID]
    files: Annotated[list[RepresentationFileModel] | None, FILES] = None
    traits: Annotated[dict[str, Any] | None, TRAITS] = None
    path: Annotated[str | None, REPRESENTATION_PATH] = None
    belongs_to_hero: Annotated[bool | None, BELONGS_TO_HERO] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True
    own_attrib: Annotated[list[str] | None, OWN_ATTRIB] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    created_at: Annotated[datetime | None, CREATED_AT] = Field(
        default_factory=datetime.now
    )
    updated_at: Annotated[datetime | None, UPDATED_AT] = Field(
        default_factory=datetime.now
    )


class RepresentationPostModel(EntityModel):
    entity_type: ClassVar[str] = "representation"

    id: Annotated[str | None, ENTITY_ID] = Field(default_factory=create_uuid)
    name: Annotated[str, REPRESENTATION_NAME]
    version_id: Annotated[str, VERSION_ID]
    files: Annotated[list[RepresentationFileModel] | None, FILES] = None
    traits: Annotated[dict[str, Any] | None, TRAITS] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True


class RepresentationPatchModel(EntityModel):
    entity_type: ClassVar[str] = "representation"

    name: Annotated[str | None, REPRESENTATION_NAME] = None
    version_id: Annotated[str | None, VERSION_ID] = None
    files: Annotated[list[RepresentationFileModel] | None, FILES] = None
    traits: Annotated[dict[str, Any] | None, TRAITS] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True

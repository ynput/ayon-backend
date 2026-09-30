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
    THUMBNAIL_ID,
    UPDATED_AT,
    UPDATED_BY,
    EntityModel,
)
from ayon_server.models.attrib_values import AttribDict
from ayon_server.types import (
    ENTITY_ID_EXAMPLE,
    ENTITY_ID_REGEX,
    LABEL_REGEX,
    NAME_REGEX,
    Field,
)
from ayon_server.utils import create_uuid

FOLDER_NAME = Field(title="Folder name", pattern=NAME_REGEX, example="bush")
FOLDER_LABEL = Field(title="Folder label", pattern=LABEL_REGEX, example="bush")
FOLDER_TYPE = Field(title="Folder type", example="Asset")
PARENT_ID = Field(
    title="Parent ID",
    description="Parent folder ID in the hierarchy",
    pattern=ENTITY_ID_REGEX,
    example=ENTITY_ID_EXAMPLE,
)
FOLDER_PATH = Field(title="Path", example="/assets/characters/xenomorph")
HAS_VERSIONS = Field(title="Has versions", example=True)


class FolderModel(EntityModel):
    entity_type: ClassVar[str] = "folder"

    id: Annotated[str | None, ENTITY_ID] = Field(default_factory=create_uuid)
    name: Annotated[str, FOLDER_NAME]
    label: Annotated[str | None, FOLDER_LABEL] = None
    folder_type: Annotated[str | None, FOLDER_TYPE] = None
    parent_id: Annotated[str | None, PARENT_ID] = None
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    path: Annotated[str | None, FOLDER_PATH] = None
    has_versions: Annotated[bool | None, HAS_VERSIONS] = None
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


class FolderPostModel(EntityModel):
    entity_type: ClassVar[str] = "folder"

    id: Annotated[str | None, ENTITY_ID] = Field(default_factory=create_uuid)
    name: Annotated[str, FOLDER_NAME]
    label: Annotated[str | None, FOLDER_LABEL] = None
    folder_type: Annotated[str | None, FOLDER_TYPE] = None
    parent_id: Annotated[str | None, PARENT_ID] = None
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True


class FolderPatchModel(EntityModel):
    entity_type: ClassVar[str] = "folder"

    name: Annotated[str | None, FOLDER_NAME] = None
    label: Annotated[str | None, FOLDER_LABEL] = None
    folder_type: Annotated[str | None, FOLDER_TYPE] = None
    parent_id: Annotated[str | None, PARENT_ID] = None
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True

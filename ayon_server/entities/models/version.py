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
    TASK_ID,
    THUMBNAIL_ID,
    UPDATED_AT,
    UPDATED_BY,
    EntityModel,
)
from ayon_server.models.attrib_values import AttribDict
from ayon_server.types import (
    ENTITY_ID_EXAMPLE,
    ENTITY_ID_REGEX,
    USER_NAME_REGEX,
    Field,
)
from ayon_server.utils import create_uuid

VERSION = Field(title="Version", description="Version number", example=1)
PRODUCT_ID = Field(
    title="Product ID",
    description="ID of the parent product",
    pattern=ENTITY_ID_REGEX,
    example=ENTITY_ID_EXAMPLE,
)
AUTHOR = Field(title="Author", pattern=USER_NAME_REGEX, example="john_doe")
VERSION_PATH = Field(
    title="Path",
    example="/assets/characters/xenomorph/modelMain/v003",
)


class VersionModel(EntityModel):
    entity_type: ClassVar[str] = "version"

    id: Annotated[str | None, ENTITY_ID] = Field(default_factory=create_uuid)
    version: Annotated[int, VERSION]
    product_id: Annotated[str, PRODUCT_ID]
    task_id: Annotated[str | None, TASK_ID] = None
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    author: Annotated[str | None, AUTHOR] = None
    path: Annotated[str | None, VERSION_PATH] = None
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


class VersionPostModel(EntityModel):
    entity_type: ClassVar[str] = "version"

    id: Annotated[str | None, ENTITY_ID] = Field(default_factory=create_uuid)
    version: Annotated[int, VERSION]
    product_id: Annotated[str, PRODUCT_ID]
    task_id: Annotated[str | None, TASK_ID] = None
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    author: Annotated[str | None, AUTHOR] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True


class VersionPatchModel(EntityModel):
    entity_type: ClassVar[str] = "version"

    version: Annotated[int | None, VERSION] = None
    product_id: Annotated[str | None, PRODUCT_ID] = None
    task_id: Annotated[str | None, TASK_ID] = None
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    author: Annotated[str | None, AUTHOR] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True

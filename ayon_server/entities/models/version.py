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
    ProjectLevelEntityModel,
)
from ayon_server.models.attrib_values import AttribDict
from ayon_server.types import (
    ENTITY_ID_EXAMPLE,
    ENTITY_ID_REGEX,
    USER_NAME_REGEX,
    Field,
)
from ayon_server.utils import create_uuid

#
# Version specific fields
#

VERSION = Field(
    title="Version",
    description="Version number",
    examples=[1],
)

PRODUCT_ID = Field(
    title="Product ID",
    description="ID of the parent product",
    pattern=ENTITY_ID_REGEX,
    examples=[ENTITY_ID_EXAMPLE],
)

AUTHOR = Field(
    title="Author",
    pattern=USER_NAME_REGEX,
    examples=["john.doe"],
)

VERSION_PATH = Field(
    title="Path",
    examples=["/assets/characters/xenomorph/modelMain/v003"],
)

#
# Version models
#


class VersionModel(ProjectLevelEntityModel):
    entity_type: ClassVar[str] = "version"

    id: Annotated[str, ENTITY_ID] = Field(default_factory=create_uuid)
    version: Annotated[int, VERSION]
    product_id: Annotated[str, PRODUCT_ID]
    task_id: Annotated[str | None, TASK_ID] = None
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    author: Annotated[str | None, AUTHOR] = None
    path: Annotated[str | None, VERSION_PATH] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any], DATA] = Field(default_factory=dict)
    active: Annotated[bool, ACTIVE] = True
    own_attrib: Annotated[list[str], OWN_ATTRIB] = Field(default_factory=list)
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str], TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    created_at: Annotated[datetime, CREATED_AT] = Field(default_factory=datetime.now)
    updated_at: Annotated[datetime, UPDATED_AT] = Field(default_factory=datetime.now)


class VersionPostModel(EntityModel):
    entity_type: ClassVar[str] = "version"

    id: Annotated[str, ENTITY_ID] = Field(default_factory=create_uuid)
    version: Annotated[int, VERSION]
    product_id: Annotated[str, PRODUCT_ID]
    task_id: Annotated[str | None, TASK_ID] = None
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    author: Annotated[str | None, AUTHOR] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str], TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any], DATA] = Field(default_factory=dict)
    active: Annotated[bool, ACTIVE] = True


class VersionPatchModel(EntityModel):
    entity_type: ClassVar[str] = "version"

    version: Annotated[int | None, VERSION] = None
    product_id: Annotated[str | None, PRODUCT_ID] = None
    task_id: Annotated[str | None, TASK_ID] = None
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    author: Annotated[str | None, AUTHOR] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = None
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = None
    active: Annotated[bool | None, ACTIVE] = None

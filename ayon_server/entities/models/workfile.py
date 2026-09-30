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
from ayon_server.types import Field
from ayon_server.utils import create_uuid

WORKFILE_PATH = Field(
    title="Path",
    description="Path to the workfile",
    example="{root['work']}/Project/workfiles/ma/modelMain_v001.ma",
)


class WorkfileModel(ProjectLevelEntityModel):
    entity_type: ClassVar[str] = "workfile"

    id: Annotated[str, ENTITY_ID] = Field(default_factory=create_uuid)
    path: Annotated[str, WORKFILE_PATH]
    task_id: Annotated[str, TASK_ID]
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any], DATA] = Field(default_factory=dict)
    active: Annotated[bool, ACTIVE] = True
    own_attrib: Annotated[list[str], OWN_ATTRIB] = Field(default_factory=list)
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str], TAGS] = Field(default_factory=list)
    created_at: Annotated[datetime, CREATED_AT] = Field(default_factory=datetime.now)
    updated_at: Annotated[datetime, UPDATED_AT] = Field(default_factory=datetime.now)


class WorkfilePostModel(EntityModel):
    entity_type: ClassVar[str] = "workfile"

    id: Annotated[str, ENTITY_ID] = Field(default_factory=create_uuid)
    path: Annotated[str, WORKFILE_PATH]
    task_id: Annotated[str, TASK_ID]
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str], TAGS] = Field(default_factory=list)
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any], DATA] = Field(default_factory=dict)
    active: Annotated[bool, ACTIVE] = True


class WorkfilePatchModel(EntityModel):
    entity_type: ClassVar[str] = "workfile"

    path: Annotated[str | None, WORKFILE_PATH] = None
    task_id: Annotated[str | None, TASK_ID] = None
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = None
    active: Annotated[bool | None, ACTIVE] = None

from datetime import datetime
from typing import Annotated, Any, ClassVar

from ayon_server.entities.models.common import (
    ACTIVE,
    ATTRIB,
    CREATED_AT,
    CREATED_BY,
    DATA,
    ENTITY_ID,
    FOLDER_ID,
    OWN_ATTRIB,
    STATUS,
    TAGS,
    THUMBNAIL_ID,
    UPDATED_AT,
    UPDATED_BY,
    EntityModel,
    ProjectLevelEntityModel,
)
from ayon_server.models.attrib_values import AttribDict
from ayon_server.types import LABEL_REGEX, NAME_REGEX, Field
from ayon_server.utils import create_uuid

TASK_NAME = Field(title="Task name", pattern=NAME_REGEX, example="modeling")
TASK_LABEL = Field(
    title="Task label",
    pattern=LABEL_REGEX,
    example="Modeling of a model",
)
TASK_TYPE = Field(title="Task type", example="Modeling")
ASSIGNEES = Field(
    title="Assignees",
    description="List of users assigned to the task",
    example=["john_doe", "jane_doe"],
)
TASK_PATH = Field(title="Path", example="/assets/characters/xenomorph/modeling")


class TaskModel(ProjectLevelEntityModel):
    entity_type: ClassVar[str] = "task"

    id: Annotated[str, ENTITY_ID] = Field(default_factory=create_uuid)
    name: Annotated[str, TASK_NAME]
    label: Annotated[str | None, TASK_LABEL] = None
    task_type: Annotated[str, TASK_TYPE]
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    assignees: Annotated[list[str], ASSIGNEES] = Field(default_factory=list)
    folder_id: Annotated[str | None, FOLDER_ID] = None
    path: Annotated[str | None, TASK_PATH] = None
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


class TaskPostModel(EntityModel):
    entity_type: ClassVar[str] = "task"

    id: Annotated[str, ENTITY_ID] = Field(default_factory=create_uuid)
    name: Annotated[str, TASK_NAME]
    label: Annotated[str | None, TASK_LABEL] = None
    task_type: Annotated[str, TASK_TYPE]
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    assignees: Annotated[list[str], ASSIGNEES] = Field(default_factory=list)
    folder_id: Annotated[str | None, FOLDER_ID] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str], TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any], DATA] = Field(default_factory=dict)
    active: Annotated[bool, ACTIVE] = True


class TaskPatchModel(EntityModel):
    entity_type: ClassVar[str] = "task"

    name: Annotated[str | None, TASK_NAME] = None
    label: Annotated[str | None, TASK_LABEL] = None
    task_type: Annotated[str | None, TASK_TYPE] = None
    thumbnail_id: Annotated[str | None, THUMBNAIL_ID] = None
    assignees: Annotated[list[str] | None, ASSIGNEES] = None
    folder_id: Annotated[str | None, FOLDER_ID] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = None
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = None
    active: Annotated[bool | None, ACTIVE] = None

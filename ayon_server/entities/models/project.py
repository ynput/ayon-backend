from datetime import datetime
from typing import Annotated, Any, ClassVar

from ayon_server.entities.models.common import (
    ACTIVE,
    ATTRIB,
    CREATED_AT,
    DATA,
    OWN_ATTRIB,
    UPDATED_AT,
    EntityMainModel,
    EntityModel,
)
from ayon_server.entities.models.submodels import LinkTypeModel
from ayon_server.models.attrib_values import AttribDict
from ayon_server.types import LABEL_REGEX, PROJECT_NAME_REGEX, Field

PROJECT_NAME = Field(
    title="Project name",
    description="Unique name of the project",
    pattern=PROJECT_NAME_REGEX,
    example="awesome_project",
)
PROJECT_CODE = Field(title="Project code", pattern=PROJECT_NAME_REGEX, example="prj")
PROJECT_LABEL = Field(
    title="Project label",
    pattern=LABEL_REGEX,
    example="My awesome project",
)
FOLDER_TYPES = Field(
    title="Folder types",
    example=[
        {"name": "Folder", "icon": "folder"},
        {"name": "Asset", "icon": "folder"},
        {"name": "Shot", "icon": "folder"},
    ],
)
TASK_TYPES = Field(
    title="Task types",
    example=[
        {"name": "Rigging", "icon": "rig"},
        {"name": "Modeling", "icon": "model"},
    ],
)
LINK_TYPES = Field(
    title="Link types",
    example=[
        {
            "name": "reference|version|version",
            "link_type": "reference",
            "input_type": "version",
            "output_type": "version",
            "data": {"color": "#ff0000"},
        },
    ],
)
STATUSES = Field(title="Statuses", example=[{"name": "Unknown"}])
PROJECT_TAGS = Field(
    title="Tags",
    description="List of tags available to set on entities.",
    example=[{"name": "Unknown"}],
)
PROJECT_CONFIG = Field(title="Project config")
SKELETON = Field(title="Skeleton project", example=True)


class ProjectModel(EntityMainModel):
    entity_type: ClassVar[str] = "project"

    name: Annotated[str, PROJECT_NAME]
    code: Annotated[str, PROJECT_CODE]
    label: Annotated[str | None, PROJECT_LABEL] = None
    library: bool = False
    folder_types: Annotated[list[Any], FOLDER_TYPES] = Field(default_factory=list)
    task_types: Annotated[list[Any], TASK_TYPES] = Field(default_factory=list)
    link_types: Annotated[list[LinkTypeModel], LINK_TYPES] = Field(default_factory=list)
    statuses: Annotated[list[Any], STATUSES] = Field(default_factory=list)
    tags: Annotated[list[Any], PROJECT_TAGS] = Field(default_factory=list)
    config: Annotated[dict[str, Any], PROJECT_CONFIG] = Field(default_factory=dict)
    skeleton: Annotated[bool | None, SKELETON] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any], DATA] = Field(default_factory=dict)
    active: Annotated[bool, ACTIVE] = True
    own_attrib: Annotated[list[str], OWN_ATTRIB] = Field(default_factory=list)
    created_at: Annotated[datetime, CREATED_AT] = Field(default_factory=datetime.now)
    updated_at: Annotated[datetime, UPDATED_AT] = Field(default_factory=datetime.now)


class ProjectPostModel(EntityModel):
    entity_type: ClassVar[str] = "project"

    code: Annotated[str, PROJECT_CODE]
    label: Annotated[str | None, PROJECT_LABEL] = None
    library: bool = False
    folder_types: Annotated[list[Any], FOLDER_TYPES] = Field(default_factory=list)
    task_types: Annotated[list[Any], TASK_TYPES] = Field(default_factory=list)
    link_types: Annotated[list[LinkTypeModel], LINK_TYPES] = Field(default_factory=list)
    statuses: Annotated[list[Any], STATUSES] = Field(default_factory=list)
    tags: Annotated[list[Any], PROJECT_TAGS] = Field(default_factory=list)
    config: Annotated[dict[str, Any], PROJECT_CONFIG] = Field(default_factory=dict)
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any], DATA] = Field(default_factory=dict)
    active: Annotated[bool, ACTIVE] = True


class ProjectPatchModel(EntityModel):
    entity_type: ClassVar[str] = "project"

    code: Annotated[str | None, PROJECT_CODE] = None
    label: Annotated[str | None, PROJECT_LABEL] = None
    library: bool | None = None
    folder_types: Annotated[list[Any] | None, FOLDER_TYPES] = None
    task_types: Annotated[list[Any] | None, TASK_TYPES] = None
    link_types: Annotated[list[LinkTypeModel] | None, LINK_TYPES] = None
    statuses: Annotated[list[Any] | None, STATUSES] = None
    tags: Annotated[list[Any] | None, PROJECT_TAGS] = None
    config: Annotated[dict[str, Any] | None, PROJECT_CONFIG] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = None
    active: Annotated[bool | None, ACTIVE] = None

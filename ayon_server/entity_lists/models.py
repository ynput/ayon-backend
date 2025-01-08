from typing import Annotated

from ayon_server.types import Field, OPModel, ProjectLevelEntityType
from ayon_server.utils import create_uuid


class EntityListItem(OPModel):
    id: Annotated[str, Field(default_factory=create_uuid)]
    position: Annotated[int, Field(..., example=1)]
    entity_type: ProjectLevelEntityType = Field(..., example="task")
    entity_id: str = Field(..., example="1234567890")


class EntityList(OPModel):
    id: Annotated[str, Field(default_factory=create_uuid)]
    label: Annotated[str, Field(..., example="My List")]
    list_type: Annotated[str, Field(..., example="heap")]

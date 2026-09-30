from datetime import datetime
from typing import Annotated, Any, ClassVar

from ayon_server.entities.models.common import (
    ACTIVE,
    ATTRIB,
    CREATED_AT,
    DATA,
    OWN_ATTRIB,
    UPDATED_AT,
    EntityModel,
)
from ayon_server.models.attrib_values import AttribDict
from ayon_server.types import USER_NAME_REGEX, Field

USER_NAME = Field(
    title="User name",
    description="Unique name of the user",
    pattern=USER_NAME_REGEX,
    example="awesome_user",
)
UI_EXPOSURE_LEVEL = Field(title="UI Exposure Level", example=100)


class UserModel(EntityModel):
    entity_type: ClassVar[str] = "user"

    name: Annotated[str, USER_NAME]
    ui_exposure_level: Annotated[int | None, UI_EXPOSURE_LEVEL] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True
    own_attrib: Annotated[list[str] | None, OWN_ATTRIB] = None
    created_at: Annotated[datetime | None, CREATED_AT] = Field(
        default_factory=datetime.now
    )
    updated_at: Annotated[datetime | None, UPDATED_AT] = Field(
        default_factory=datetime.now
    )


class UserPostModel(EntityModel):
    entity_type: ClassVar[str] = "user"

    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True


class UserPatchModel(EntityModel):
    entity_type: ClassVar[str] = "user"

    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True

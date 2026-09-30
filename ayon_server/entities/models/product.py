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
    UPDATED_AT,
    UPDATED_BY,
    EntityModel,
)
from ayon_server.models.attrib_values import AttribDict
from ayon_server.types import NAME_REGEX, Field
from ayon_server.utils import create_uuid

PRODUCT_NAME = Field(
    title="Product name",
    description="Name of the product",
    pattern=NAME_REGEX,
    example="modelMain",
)
PRODUCT_TYPE = Field(
    title="Product type",
    description="Product type",
    pattern=NAME_REGEX,
    example="modelMain",
)
PRODUCT_BASE_TYPE = Field(
    title="Product base type",
    description="Product base type",
    pattern=NAME_REGEX,
    example="model",
)
PRODUCT_PATH = Field(title="Path", example="/assets/characters/xenomorph/modelMain")


class ProductModel(EntityModel):
    entity_type: ClassVar[str] = "product"

    id: Annotated[str | None, ENTITY_ID] = Field(default_factory=create_uuid)
    name: Annotated[str, PRODUCT_NAME]
    folder_id: Annotated[str, FOLDER_ID]
    product_type: Annotated[str, PRODUCT_TYPE]
    product_base_type: Annotated[str | None, PRODUCT_BASE_TYPE] = None
    path: Annotated[str | None, PRODUCT_PATH] = None
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


class ProductPostModel(EntityModel):
    entity_type: ClassVar[str] = "product"

    id: Annotated[str | None, ENTITY_ID] = Field(default_factory=create_uuid)
    name: Annotated[str, PRODUCT_NAME]
    folder_id: Annotated[str, FOLDER_ID]
    product_type: Annotated[str, PRODUCT_TYPE]
    product_base_type: Annotated[str | None, PRODUCT_BASE_TYPE] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True


class ProductPatchModel(EntityModel):
    entity_type: ClassVar[str] = "product"

    name: Annotated[str | None, PRODUCT_NAME] = None
    folder_id: Annotated[str | None, FOLDER_ID] = None
    product_type: Annotated[str | None, PRODUCT_TYPE] = None
    product_base_type: Annotated[str | None, PRODUCT_BASE_TYPE] = None
    status: Annotated[str | None, STATUS] = None
    tags: Annotated[list[str] | None, TAGS] = Field(default_factory=list)
    created_by: Annotated[str | None, CREATED_BY] = None
    updated_by: Annotated[str | None, UPDATED_BY] = None
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)
    data: Annotated[dict[str, Any] | None, DATA] = Field(default_factory=dict)
    active: Annotated[bool | None, ACTIVE] = True

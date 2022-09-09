from typing import Any

from pydantic import Field
from fastapi import APIRouter, Depends

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user
from openpype.entities import UserEntity
from openpype.lib.postgres import Postgres
from openpype.types import OPModel

#
# Router
#


router = APIRouter(
    prefix="/attributes",
    tags=["Attributes"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)


class AttributeData(OPModel):
    type: str
    title: str | None = Field(None, title="Nice field title")
    description: str | None = Field(None, title="Field description")
    example: Any = Field(None, title="Field example")
    default: Any = Field(None, title="Field default value")
    gt: int | float | None = Field(None, title="Greater than")
    ge: int | float | None = Field(None, title="Geater or equal")
    lt: int | float | None = Field(None, title="Less")
    le: int | float | None = Field(None, title="Less or equal")
    min_length: int | None = Field(None, title="Minimum length")
    max_length: int | None = Field(title="Maximum length")
    min_items: int | None = Field(title="Minimum items")
    max_items: int | None = Field(title="Maximum items")
    regex: int | None = Field(title="Field regex")


class AttributeListItem(OPModel):
    name: str
    position: int
    scope: list[str]
    builtin: bool
    data: AttributeData


class AttributeListResponseModel(OPModel):
    attributes: list[AttributeListItem]


@router.get("")
async def get_attribute_list(user: UserEntity = Depends(dep_current_user)):

    query = "SELECT * FROM attributes ORDER BY position"

    attributes: list[AttributeListItem] = []
    async for row in Postgres.iterate(query):
        attributes.append(AttributeListItem(**row))

    return AttributeListResponseModel(attributes=attributes)

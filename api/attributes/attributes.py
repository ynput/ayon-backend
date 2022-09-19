from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import Field

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user
from openpype.entities import UserEntity
from openpype.lib.postgres import Postgres
from openpype.types import OPModel
from openpype.utils import SQLTool

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
    max_length: int | None = Field(None, title="Maximum length")
    min_items: int | None = Field(None, title="Minimum items")
    max_items: int | None = Field(None, title="Maximum items")
    regex: int | None = Field(None, title="Field regex")


class AttributeListItem(OPModel):
    name: str
    position: int
    scope: list[str]
    builtin: bool
    data: AttributeData


class AttributeListModel(OPModel):
    attributes: list[AttributeListItem]


@router.get("")
async def get_attribute_list(user: UserEntity = Depends(dep_current_user)):

    query = "SELECT * FROM attributes ORDER BY position"

    attributes: list[AttributeListItem] = []
    async for row in Postgres.iterate(query):
        attributes.append(AttributeListItem(**row))

    return AttributeListModel(attributes=attributes)


@router.put("")
async def set_attribute_list(
    payload: AttributeListModel,
    user: UserEntity = Depends(dep_current_user),
):

    new_attributes = payload.attributes
    new_names = [attribute.name for attribute in new_attributes]

    # Delete deleted
    query = f"""
        DELETE FROM attributes
        WHERE builtin IS NOT TRUE
        AND name NOT IN {SQLTool.array(new_names)}
    """
    await Postgres.execute(query)

    for attr in new_attributes:
        query = """
        INSERT INTO attributes
        (name, position, scope, data)
        VALUES
        ($1, $2, $3, $4)
        ON CONFLICT (name)
        DO UPDATE SET
            position = $2,
            scope = $3,
            data = $4
        """

        await Postgres.execute(
            query,
            attr.name,
            attr.position,
            attr.scope,
            attr.data.dict(),
        )

    return Response(status_code=204)

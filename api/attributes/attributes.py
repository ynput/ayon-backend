from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import Field

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_attribute_name, dep_current_user
from openpype.entities import UserEntity
from openpype.exceptions import ForbiddenException, NotFoundException
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


class AttributeNameModel(OPModel):
    name: str = Field(
        ...,
        name="Attribute name",
        regex="^[a-zA-Z0-9]{2,30}$",
    )


class AttributePutModel(OPModel):
    position: int = Field(
        ...,
        title="Positon",
        description="Default order",
    )
    scope: list[str]
    builtin: bool
    data: AttributeData


class AttributeModel(AttributePutModel, AttributeNameModel):
    pass


class GetAttributeListModel(OPModel):
    attributes: list[AttributeModel] = Field(
        default_factory=list,
        title="Attributes configuration",
    )


class SetAttributeListModel(GetAttributeListModel):
    delete_missing: bool = Field(
        False,
        title="Delete missing",
        description="Delete custom attributes not included"
        "in the payload from the database.",
    )


@router.get("", response_model=GetAttributeListModel)
async def get_attribute_list(user: UserEntity = Depends(dep_current_user)):
    """Return a list of attributes and their configuration."""

    query = "SELECT * FROM attributes ORDER BY position"
    attributes: list[AttributeModel] = []
    async for row in Postgres.iterate(query):
        attributes.append(AttributeModel(**row))
    return GetAttributeListModel(attributes=attributes)


@router.put("", response_class=Response)
async def set_attribute_list(
    payload: SetAttributeListModel,
    user: UserEntity = Depends(dep_current_user),
):
    """
    Set the attribute configuration for all (or a subset of) attributes
    """

    if not user.is_admin:
        raise ForbiddenException("Only administrators are allowed to modify attributes")

    new_attributes = payload.attributes
    new_names = [attribute.name for attribute in new_attributes]

    # Delete deleted
    if payload.delete_missing:
        await Postgres.execute(
            f"""
            DELETE FROM attributes
            WHERE builtin IS NOT TRUE
            AND name NOT IN {SQLTool.array(new_names)}
            """
        )

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


@router.get("/{attribute_name}", response_model=AttributeModel)
async def get_attribute_config(
    user: UserEntity = Depends(dep_current_user),
    attribute_name: str = Depends(dep_attribute_name),
):
    """Return the configuration for a single attribute."""

    query = "SELECT * FROM attributes WHERE name = $1"
    async for row in Postgres.iterate(query, attribute_name):
        return AttributeModel(**row)
    raise NotFoundException(f"Attribute {attribute_name} not found")


@router.put("/{attribute_name}", response_class=Response)
async def set_attribute_config(
    payload: AttributePutModel,
    user: UserEntity = Depends(dep_current_user),
    attribute_name: str = Depends(dep_attribute_name),
):
    """Update attribute configuration"""

    if not user.is_admin:
        raise ForbiddenException("Only administrators are allowed to modify attributes")

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
        attribute_name,
        payload.position,
        payload.scope,
        payload.data.dict(),
    )
    return Response(status_code=204)


@router.delete("/{attribute_name}", response_class=Response)
async def delete_attribute(
    user: UserEntity = Depends(dep_current_user),
    attribute_name: str = Depends(dep_attribute_name),
):
    if not user.is_admin:
        raise ForbiddenException("Only administrators are allowed to delete attributes")

    query = "DELETE FROM attributes WHERE name = $1"
    await Postgres.iterate(query, attribute_name)
    return Response(status_code=204)

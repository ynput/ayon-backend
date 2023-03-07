from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import Field

from ayon_server.api import ResponseFactory
from ayon_server.api.dependencies import dep_attribute_name, dep_current_user
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import (
    AttributeType,
    OPModel,
    ProjectLevelEntityType,
    TopLevelEntityType,
)

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


class AttributeEnumItem(OPModel):
    """Attribute enum item."""

    value: Any = Field(..., title="Enum value")
    label: str = Field(..., title="Enum label")


class AttributeData(OPModel):
    type: AttributeType = Field(
        ...,
        title="Type",
        description="Type of attribute value",
        example="string",
    )
    title: str | None = Field(
        None,
        title="Title",
        description="Nice, human readable title of the attribute",
        example="My attribute",
    )
    description: str | None = Field(
        None,
        title="Field description",
        example="Value of my attribute",
    )
    example: Any = Field(
        None,
        title="Field example",
        description="Example value of the field.",
        example="value1",
    )
    default: Any = Field(
        None,
        title="Field default value",
        description="Default value for the attribute. Do not set for list types.",
    )
    gt: int | float | None = Field(None, title="Greater than")
    ge: int | float | None = Field(None, title="Geater or equal")
    lt: int | float | None = Field(None, title="Less")
    le: int | float | None = Field(None, title="Less or equal")
    min_length: int | None = Field(None, title="Minimum length")
    max_length: int | None = Field(None, title="Maximum length")
    min_items: int | None = Field(
        None,
        title="Minimum items",
        description="Minimum number of items in list type.",
    )
    max_items: int | None = Field(
        None,
        title="Maximum items",
        description="Only for list types. Maximum number of items in the list.",
    )
    regex: str | None = Field(
        None,
        title="Field regex",
        description="Only for string types. The value must match this regex.",
        example="^[a-zA-Z0-9_]+$",
    )

    enum: list[AttributeEnumItem] | None = Field(
        None,
        title="Field enum",
        description="List of enum items used for displaying select/multiselect widgets",
        example=[
            {"value": "value1", "label": "Value 1"},
            {"value": "value2", "label": "Value 2"},
            {"value": "value3", "label": "Value 3"},
        ],
    )


class AttributeNameModel(OPModel):
    name: str = Field(
        ...,
        name="Attribute name",
        regex="^[a-zA-Z0-9]{2,30}$",
        example="my_attribute",
    )


class AttributePutModel(OPModel):
    position: int = Field(
        ...,
        title="Positon",
        description="Default order",
        example=12,
    )
    scope: list[ProjectLevelEntityType | TopLevelEntityType] = Field(
        default_factory=list,
        title="Scope",
        description="List of entity types the attribute is available on",
        example=["folder", "task"],
    )
    builtin: bool = Field(
        ...,
        title="Builtin",
        description="Is attribute builtin. Built-in attributes cannot be removed.",
    )
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


@router.get("")
async def get_attribute_list(
    user: UserEntity = Depends(dep_current_user),
) -> GetAttributeListModel:
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
            """
            DELETE FROM attributes
            WHERE builtin IS NOT TRUE
            AND NOT name = ANY($1)
            """,
            new_names,
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
            attr.data.dict(exclude_none=True),
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
        payload.data.dict(exclude_none=True),
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

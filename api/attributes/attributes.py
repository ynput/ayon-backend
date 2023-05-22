from typing import Any

from fastapi import APIRouter
from pydantic import Field, ValidationError

from ayon_server.api.dependencies import AttributeName, CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import (
    AttributeType,
    OPModel,
    ProjectLevelEntityType,
    TopLevelEntityType,
)

router = APIRouter(prefix="/attributes", tags=["Attributes"])


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
    inherit: bool = Field(
        True,
        title="Inherit",
        description="Inherit the attribute value from the parent entity.",
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
        False,
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


async def save_attribute(attribute: AttributeModel):
    query = """
    INSERT INTO attributes
    (name, position, scope, data)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (name)
    DO UPDATE SET position = $2, scope = $3, data = $4
    """

    await Postgres.execute(
        query,
        attribute.name,
        attribute.position,
        attribute.scope,
        attribute.data.dict(exclude_none=True),
    )


async def list_raw_attributes() -> list[dict[str, Any]]:
    """Return a list of attributes as they are stored in the DB"""

    query = "SELECT * FROM attributes ORDER BY position"
    attributes: list[AttributeModel] = []
    async for row in Postgres.iterate(query):
        attributes.append(dict(row))
    return attributes


async def list_attributes() -> list[AttributeModel]:
    """Return a list of attributes and their configuration.

    Skip attributes with invalid configuration.
    """

    attr_list = await list_raw_attributes()
    result = []
    for attr in attr_list:
        try:
            result.append(AttributeModel(**attr))
        except ValidationError:
            pass
    return result


async def remove_attribute(name: str):
    query = "DELETE FROM attributes WHERE name = $1"
    await Postgres.execute(query, name)


#
# REST endpoints
#


@router.get("")
async def get_attribute_list(user: CurrentUser) -> GetAttributeListModel:
    """Return a list of attributes and their configuration."""

    attributes = await list_attributes()
    return GetAttributeListModel(attributes=attributes)


@router.put("", status_code=204)
async def set_attribute_list(
    payload: SetAttributeListModel,
    user: CurrentUser,
) -> EmptyResponse:
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
        await save_attribute(attr)

    return EmptyResponse()


@router.get("/{attribute_name}")
async def get_attribute_config(
    user: CurrentUser, attribute_name: AttributeName
) -> AttributeModel:
    """Return the configuration for a single attribute."""

    query = "SELECT * FROM attributes WHERE name = $1"
    async for row in Postgres.iterate(query, attribute_name):
        return AttributeModel(**row)
    raise NotFoundException(f"Attribute {attribute_name} not found")


@router.put("/{attribute_name}", status_code=204)
async def set_attribute_config(
    payload: AttributePutModel, user: CurrentUser, attribute_name: AttributeName
) -> EmptyResponse:
    """Update attribute configuration"""
    if not user.is_admin:
        raise ForbiddenException("Only administrators are allowed to modify attributes")
    attribute = AttributeModel(name=attribute_name, **payload.dict())
    await save_attribute(attribute)
    return EmptyResponse()


@router.delete("/{attribute_name}", status_code=204)
async def delete_attribute(
    user: CurrentUser, attribute_name: AttributeName
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only administrators are allowed to delete attributes")

    await remove_attribute(attribute_name)
    return EmptyResponse()

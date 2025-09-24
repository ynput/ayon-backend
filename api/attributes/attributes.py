from typing import Any

from fastapi import APIRouter
from pydantic import Field, ValidationError

from ayon_server.api.dependencies import AttributeName, CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.api.system import require_server_restart
from ayon_server.attributes.models import (
    AttributeModel,
    AttributePatchModel,
    AttributePutModel,
)
from ayon_server.attributes.validate_attribute_data import validate_attribute_data
from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import OPModel

router = APIRouter(prefix="/attributes", tags=["Attributes"])


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


async def save_attribute(attribute: AttributeModel) -> None:
    """Save attribute configuration to the database.

    Additionally performs validation of the attribute data and updates
    the enumerator in the running instance.
    """
    query = """
    INSERT INTO attributes
    (name, position, scope, data)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (name)
    DO UPDATE SET position = $2, scope = $3, data = $4
    """

    validate_attribute_data(attribute.name, attribute.data)

    await Postgres.execute(
        query,
        attribute.name,
        attribute.position,
        attribute.scope,
        attribute.data.dict(exclude_none=True),
    )

    # TODO: The following code does not support horizontal scaling!!
    # Notify other instances instead and reload the attribute library

    if (enum := attribute.data.enum) is not None:
        for name, field in ProjectEntity.model.attrib_model.__fields__.items():
            if name != attribute.name:
                continue

            field_enum = field.field_info.extra.get("enum")
            if field_enum is None:
                continue
            field_enum.clear()
            field_enum.extend(enum)

        for name, field in ProjectEntity.model.attrib_model.__fields__.items():
            if name != attribute.name:
                continue
            field_enum = field.field_info.extra.get("enum")


async def list_raw_attributes() -> list[dict[str, Any]]:
    """Return a list of attributes as they are stored in the DB"""

    query = "SELECT * FROM attributes ORDER BY position"
    attributes = []
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
    Set the attribute configuration for all (or ao of) attributes
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

    await require_server_restart()
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
    payload: AttributePutModel,
    user: CurrentUser,
    attribute_name: AttributeName,
) -> EmptyResponse:
    """Update attribute configuration"""
    if not user.is_admin:
        raise ForbiddenException("Only administrators are allowed to modify attributes")
    attribute = AttributeModel(name=attribute_name, **payload.dict())
    await save_attribute(attribute)
    await require_server_restart(
        None, "Restart the server to apply the attribute changes."
    )
    return EmptyResponse()


@router.patch("/{attribute_name}", status_code=204)
async def patch_attribute_config(
    payload: AttributePatchModel, user: CurrentUser, attribute_name: AttributeName
) -> EmptyResponse:
    """Partially update attribute configuration"""

    attribute = await get_attribute_config(user, attribute_name)

    patch_payload = payload.dict(exclude_unset=True)
    patch_data = patch_payload.pop("data", {})

    requires_restart = False

    if "scope" in patch_payload or any(
        k in patch_data
        for k in (
            "type",
            "default",
            "gt",
            "ge",
            "lt",
            "le",
            "regex",
            "min_length",
            "max_length",
            "min_items",
            "max_items",
            "inherit",
        )
    ):
        requires_restart = True

        if not user.is_admin:
            raise ForbiddenException(
                "Only administrators are allowed to modify attribute configuration"
            )

    if not user.is_manager:
        raise ForbiddenException(
            "Only managers are allowed to modify attribute metadata"
        )

    for key, value in patch_payload.items():
        setattr(attribute, key, value)

    for key, value in patch_data.items():
        setattr(attribute.data, key, value)

    await save_attribute(attribute)

    if requires_restart:
        await require_server_restart(
            None, "Restart the server to apply the attribute changes."
        )
    return EmptyResponse()


@router.delete("/{attribute_name}", status_code=204)
async def delete_attribute(
    user: CurrentUser, attribute_name: AttributeName
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only administrators are allowed to delete attributes")

    await remove_attribute(attribute_name)
    await require_server_restart(
        None, "Restart the server to apply the attribute changes."
    )
    return EmptyResponse()

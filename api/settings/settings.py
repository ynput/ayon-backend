from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel, Field

from openpype.utils import json_loads
from openpype.lib.postgres import Postgres

router = APIRouter(prefix="", include_in_schema=False)


class AttributeModel(BaseModel):
    name: str
    title: str
    example: str
    description: str
    attribType: str
    scope: list[str] = Field(default_factory=list)
    builtIn: bool
    writable: bool


class SettingsResponseModel(BaseModel):
    attributes: list[AttributeModel] = Field(
        default_factory=list,
        description="List of attributes user has access to"
    )


@router.get("/settings", response_model=SettingsResponseModel)
async def get_settings():

    query = "SELECT name, scope, builtin, data FROM attributes ORDER BY position"

    attributes: list[AttributeModel] = []
    async for row in Postgres.iterate(query):
        data: dict[str, Any] = json_loads(row["data"])

        # TODO: skip attributes user does not have read access to
        # TODO: set writable flag according to user rights

        attributes.append(
            AttributeModel(
                name=row["name"],
                title=data.get("title", row["name"]),
                example=str(data.get("example", "")),
                description=data.get("description", ""),
                scope=row["scope"],
                attribType=data.get("type", "string"),
                builtIn=row["builtin"],
                writable=True
            )
        )

    return SettingsResponseModel(
        attributes=attributes
    )

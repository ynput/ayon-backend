import time
from typing import Any

from fastapi import APIRouter, Depends

from openpype.api import dep_current_user_optional
from openpype.api.metadata import VERSION
from openpype.entities import UserEntity
from openpype.lib.postgres import Postgres
from openpype.types import Field, OPModel

router = APIRouter(prefix="/info")
BOOT_TIME = time.time()


def get_motd():
    return "Simplicity is the ultimate sophistication."


def get_uptime():
    return time.time() - BOOT_TIME


class AttributeItemModel(OPModel):
    name: str
    title: str | None
    example: str | None
    description: str | None
    attribType: str | None
    scope: list[str] = Field(default_factory=list)
    builtIn: bool
    writable: bool


class InfoResponseModel(OPModel):
    motd: str = Field(default_factory=get_motd)
    version: str = Field(VERSION)
    uptime: float = Field(default_factory=get_uptime)
    user: UserEntity.model.main_model | None = Field(None)  # type: ignore
    attributes: list[AttributeItemModel] | None = Field(None)


async def get_additional_info(user: UserEntity):

    attributes: list[AttributeItemModel] = []
    query = "SELECT name, scope, builtin, data FROM attributes ORDER BY position"
    async for row in Postgres.iterate(query):
        data: dict[str, Any] = row["data"]

        # TODO: skip attributes user does not have read access to
        # TODO: set writable flag according to user rights

        attributes.append(
            AttributeItemModel(
                name=row["name"],
                title=data.get("title", row["name"]),
                example=str(data.get("example", "")),
                description=data.get("description", ""),
                scope=row["scope"],
                attribType=data.get("type", "string"),
                builtIn=row["builtin"],
                writable=True,
            )
        )

    return {"attributes": attributes}


@router.get("", response_model=InfoResponseModel, response_model_exclude_none=True)
async def get_site_info(
    current_user: UserEntity | None = Depends(dep_current_user_optional),
):
    additional_info = {}
    if current_user:
        additional_info = await get_additional_info(current_user)
    user_payload = current_user.payload if (current_user is not None) else None
    return InfoResponseModel(user=user_payload, **additional_info)

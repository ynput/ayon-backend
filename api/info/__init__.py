import time

from attributes.attributes import AttributeModel, get_attribute_list
from fastapi import APIRouter, Depends

from openpype.api import dep_current_user_optional
from openpype.api.metadata import VERSION
from openpype.entities import UserEntity
from openpype.types import Field, OPModel

router = APIRouter(prefix="/info", tags=["Site info"])
BOOT_TIME = time.time()


def get_motd():
    return "Simplicity is the ultimate sophistication."


def get_uptime():
    return time.time() - BOOT_TIME


class InfoResponseModel(OPModel):
    motd: str = Field(default_factory=get_motd)
    version: str = Field(VERSION)
    uptime: float = Field(default_factory=get_uptime)
    user: UserEntity.model.main_model | None = Field(None)  # type: ignore
    attributes: list[AttributeModel] | None = Field(None)


async def get_additional_info(user: UserEntity):
    attr_list = await get_attribute_list(user)
    return {
        "attributes": attr_list.attributes,
    }


@router.get("", response_model=InfoResponseModel, response_model_exclude_none=True)
async def get_site_info(
    current_user: UserEntity | None = Depends(dep_current_user_optional),
):
    additional_info = {}
    if current_user:
        additional_info = await get_additional_info(current_user)
    user_payload = current_user.payload if (current_user is not None) else None
    return InfoResponseModel(user=user_payload, **additional_info)

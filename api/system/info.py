import time

from attributes.attributes import AttributeModel, get_attribute_list
from fastapi import Depends

from openpype.api import dep_current_user_optional
from openpype.api.metadata import VERSION
from openpype.config import pypeconfig
from openpype.entities import UserEntity
from openpype.types import Field, OPModel

from .router import router

BOOT_TIME = time.time()


def get_uptime():
    return time.time() - BOOT_TIME


class InfoResponseModel(OPModel):
    motd: str | None = Field(
        pypeconfig.motd,
        title="Message of the day",
        description="Instance specific message to be displayed in the login page",
    )
    version: str = Field(
        VERSION,
        title="Ayon version",
        description="Version of the Ayon API",
    )
    uptime: float = Field(default_factory=get_uptime)
    user: UserEntity.model.main_model | None = Field(None)  # type: ignore
    attributes: list[AttributeModel] | None = Field(None)


async def get_additional_info(user: UserEntity):
    attr_list = await get_attribute_list(user)
    return {
        "attributes": attr_list.attributes,
    }


@router.get(
    "/info",
    response_model=InfoResponseModel,
    response_model_exclude_none=True,
    tags=["System"],
)
async def get_site_info(
    current_user: UserEntity | None = Depends(dep_current_user_optional),
):
    """Return site information.

    This is the initial endpoint that is called when the user opens the page.
    It returns information about the site, the current user and the configuration.

    If the user is not logged in, only the message of the day and the API version
    are returned.
    """
    additional_info = {}
    if current_user:
        additional_info = await get_additional_info(current_user)
    user_payload = current_user.payload if (current_user is not None) else None
    return InfoResponseModel(user=user_payload, **additional_info)

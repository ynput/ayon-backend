from fastapi import Query
from fastapi.responses import RedirectResponse

from ayon_server.api.dependencies import CurrentUser, CurrentUserOptional
from ayon_server.api.responses import EmptyResponse
from ayon_server.config import ayonconfig
from ayon_server.exceptions import (
    ForbiddenException,
)
from ayon_server.helpers.cloud import (
    CloudUtils,
    YnputCloudInfoModel,
)
from ayon_server.types import Field, OPModel

from .router import router


class YnputConnectRequestModel(OPModel):
    """Model for the request to set the Ynput Cloud key"""

    key: str = Field(..., description="Ynput cloud key")


#
# Endpoints
#


@router.get("")
async def get_ynput_cloud_info(user: CurrentUserOptional) -> YnputCloudInfoModel:
    """
    Check whether the Ynput Cloud key is set and return the Ynput Cloud info
    """

    if user is None:
        if await CloudUtils.get_admin_exists():
            raise ForbiddenException(
                "Connecting to Ynput Cloud without login "
                "is allowed only on the first run"
            )
    elif user.is_guest:
        raise ForbiddenException("Guests cannot load Ynput Cloud information")
    return await CloudUtils.get_cloud_info()


#
# Connect and disconnect the Ynput Cloud
#


@router.get("/authorize")
async def connect_to_ynput_cloud(origin_url: str = Query(...)):
    """Redirect to Ynput cloud authorization page"""
    instance_id = await CloudUtils.get_instance_id()
    base_url = f"{ayonconfig.ynput_cloud_api_url}/api/v1/connect"
    params = f"instance_redirect={origin_url}&instance_id={instance_id}"
    return RedirectResponse(f"{base_url}?{params}")


@router.post("")
async def set_ynput_cloud_key(
    request: YnputConnectRequestModel,
    user: CurrentUserOptional,
) -> YnputCloudInfoModel:
    """Store the Ynput cloud key in the database and return the user info"""

    if user is None:
        if await CloudUtils.get_admin_exists():
            raise ForbiddenException(
                "Connecting to Ynput Cloud is allowed only on first run"
            )
    elif not user.is_admin:
        raise ForbiddenException("Only admins can set the Ynput Cloud key")

    instance_id = await CloudUtils.get_instance_id()
    cloud_info = await CloudUtils.request_cloud_info(instance_id, request.key)
    await CloudUtils.add_ynput_cloud_key(request.key)
    return cloud_info


@router.delete("")
async def delete_ynput_cloud_key(user: CurrentUser) -> EmptyResponse:
    """Remove the Ynput cloud key from the database"""
    if not user.is_admin:
        raise ForbiddenException("Only admins can remove the Ynput cloud key")
    await CloudUtils.remove_ynput_cloud_key()
    return EmptyResponse()

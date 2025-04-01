import httpx
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from ayon_server.api.dependencies import CurrentUser, CurrentUserOptional
from ayon_server.api.responses import EmptyResponse
from ayon_server.config import ayonconfig
from ayon_server.exceptions import (
    AyonException,
    BadRequestException,
    ForbiddenException,
)
from ayon_server.helpers.cloud import (
    CloudUtils,
    YnputCloudInfoModel,
)
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel

router = APIRouter(prefix="/connect", tags=["Ynput Cloud"])


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


class FeedbackTokenModel(OPModel):
    token: str


@router.get("/feedback")
async def get_feedback_token(user: CurrentUser) -> FeedbackTokenModel:
    """Generate a feedback token for the user"""

    if user.is_guest:
        raise ForbiddenException("Guest users cannot generate feedback tokens")

    headers = await CloudUtils.get_api_headers()
    res = None

    if not user.attrib.email:
        raise BadRequestException("User email is not set")

    payload = {
        "name": user.attrib.fullName or user.name,
        "email": user.attrib.email,
    }

    try:
        url = f"{ayonconfig.ynput_cloud_api_url}/api/v2/feedback"
        async with httpx.AsyncClient(headers=headers) as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            token = res.json()["token"]
    except Exception:
        logger.error("Failed to generate feedback token")
        if res is not None:
            logger.error(res.text)
        raise AyonException("Failed to generate feedback token")

    return FeedbackTokenModel(token=token)

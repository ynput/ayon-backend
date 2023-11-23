import httpx
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from ayon_server.api.dependencies import (
    CurrentUser,
    CurrentUserOptional,
    YnputCloudKey,
    YnputSiteID,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.config import ayonconfig
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.setup import admin_exists
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

router = APIRouter(
    prefix="/connect",
    tags=["YnputConnect"],
)


class YnputConnectRequestModel(OPModel):
    """Model for the request to set the Ynput connect key"""

    key: str = Field(..., description="Ynput connect key")


class YnputConnectResponseModel(OPModel):
    """Model for the response of YnputConnect user info"""

    instance_id: str = Field(
        ...,
        description="ID of the instance",
    )
    instance_name: str = Field(
        ...,
        description="Name of the instance",
        example="Ayon - staging",
    )
    org_id: str = Field(
        ...,
        description="ID of the organization",
    )
    org_name: str = Field(
        ...,
        description="Name of the organization",
        example="Ynput",
    )

    managed: bool = Field(
        default=False,
        description="Is the instance managed by Ynput Cloud?",
    )

    # backwards compatibility with the original YnputConnect
    # TODO: remove
    user_name: str = Field(..., description="User name")
    user_email: str = Field(..., description="User email")


@router.get("")
async def get_ynput_connect_info(
    user: CurrentUser, ynput_connect_key: YnputCloudKey, site_id: YnputSiteID
) -> YnputConnectResponseModel:
    """
    Check whether the Ynput connect key is set and return the Ynput connect info
    """

    headers = {
        "x-ynput-cloud-site": site_id,
        "x-ynput-cloud-key": ynput_connect_key,
    }

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        res = await client.get(
            f"{ayonconfig.ynput_cloud_api_url}/api/v1/me",
            headers=headers,
        )

    if res.status_code == 401:
        await Postgres.execute(
            """
            DELETE FROM secrets
            WHERE name = 'ynput_connect_key'
            """
        )
        raise ForbiddenException("Invalid Ynput connect key")

    data = res.json()

    return YnputConnectResponseModel(
        **data,
        user_name=data["instanceName"],
        user_email=data["orgName"],
    )


@router.get("/authorize")
async def authorize_ynput_connect(site_id: YnputSiteID, origin_url: str = Query(...)):
    """Redirect to Ynput connect authorization page"""

    base_url = f"{ayonconfig.ynput_cloud_api_url}/api/v1/connect"
    params = f"instance_redirect={origin_url}&siteid={site_id}"
    return RedirectResponse(f"{base_url}?{params}")


@router.post("")
async def set_ynput_connect_key(
    request: YnputConnectRequestModel,
    user: CurrentUserOptional,
    site_id: YnputSiteID,
) -> EmptyResponse:
    """Store the Ynput connect key in the database and return the user info"""

    if user and not user.is_admin:
        raise ForbiddenException("Only admins can set the Ynput connect key")

    if user is None:
        has_admin = await admin_exists()
        if has_admin:
            raise ForbiddenException("Connecting to Ynput is allowed only on first run")

    headers = {
        "x-ynput-cloud-site": site_id,
        "x-ynput-cloud-key": request.key,
    }

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        res = await client.get(
            f"{ayonconfig.ynput_cloud_api_url}/api/v1/me",
            headers=headers,
        )
        if res.status_code != 200:
            print(res.text)
            raise ForbiddenException("Invalid Ynput connect key")
        data = res.json()

    await Postgres.execute(
        """
        INSERT INTO secrets (name, value)
        VALUES ('ynput_cloud_key', $1)
        ON CONFLICT (name) DO UPDATE SET value = $1
        """,
        request.key,
    )

    return YnputConnectResponseModel(
        **data,
        user_name=data["instanceName"],
        user_email=data["orgName"],
    )


@router.delete("")
async def delete_ynput_connect_key(user: CurrentUser) -> EmptyResponse:
    """Remove the Ynput connect key from the database"""
    if not user.is_admin:
        raise ForbiddenException("Only admins can remove the Ynput connect key")

    await Postgres.execute("DELETE FROM secrets WHERE name = 'ynput_connect_key'")
    return EmptyResponse()

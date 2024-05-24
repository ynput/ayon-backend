import httpx
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from ayon_server.api.dependencies import CurrentUser, CurrentUserOptional
from ayon_server.api.responses import EmptyResponse
from ayon_server.config import ayonconfig
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.cloud import get_cloud_api_headers, get_instance_id
from ayon_server.helpers.setup import admin_exists
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

router = APIRouter(
    prefix="/connect",
    tags=["Ynput Cloud"],
)


class YnputConnectRequestModel(OPModel):
    """Model for the request to set the Ynput Cloud key"""

    key: str = Field(..., description="Ynput cloud key")


class YnputConnectSubscriptionModel(OPModel):
    name: str = Field(..., description="Name of the subscription")
    product_type: str = Field(..., description="Type of the subscription")


class YnputConnectResponseModel(OPModel):
    """Model for the response of Ynput Cloud user info"""

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

    collect_saturated_metrics: bool = Field(
        False,
        description="Collect saturated metrics",
    )

    managed: bool = Field(
        default=False,
        description="Is the instance managed by Ynput Cloud?",
    )

    subscriptions: list[YnputConnectSubscriptionModel] = Field(
        default_factory=list,
        description="List of subscriptions",
    )


@router.get("")
async def get_ynput_cloud_info(user: CurrentUserOptional) -> YnputConnectResponseModel:
    """
    Check whether the Ynput Cloud key is set and return the Ynput Cloud info
    """

    if user and not user.is_admin:
        raise ForbiddenException("Only admins can get the Ynput Cloud info")

    if user is None:
        has_admin = await admin_exists()
        if has_admin:
            raise ForbiddenException(
                "Connecting to Ynput Cloud is allowed only on first run"
            )

    headers = await get_cloud_api_headers()

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        res = await client.get(
            f"{ayonconfig.ynput_cloud_api_url}/api/v1/me",
            headers=headers,
        )

    if res.status_code in [401, 403]:
        await Postgres.execute(
            """
            DELETE FROM secrets
            WHERE name = 'ynput_cloud_key'
            """
        )
        raise ForbiddenException("Invalid Ynput connect key")

    res.raise_for_status()  # should not happen

    data = res.json()

    return YnputConnectResponseModel(**data)


@router.get("/authorize")
async def connect_to_ynput_cloud(origin_url: str = Query(...)):
    """Redirect to Ynput cloud authorization page"""

    instance_id = await get_instance_id()

    base_url = f"{ayonconfig.ynput_cloud_api_url}/api/v1/connect"
    params = f"instance_redirect={origin_url}&instance_id={instance_id}"
    return RedirectResponse(f"{base_url}?{params}")


@router.post("")
async def set_ynput_cloud_key(
    request: YnputConnectRequestModel,
    user: CurrentUserOptional,
) -> YnputConnectResponseModel:
    """Store the Ynput cloud key in the database and return the user info"""

    if user and not user.is_admin:
        raise ForbiddenException("Only admins can set the Ynput Cloud key")

    if user is None:
        has_admin = await admin_exists()
        if has_admin:
            raise ForbiddenException(
                "Connecting to Ynput Cloud is allowed only on first run"
            )

    instance_id = await get_instance_id()

    headers = {
        "x-ynput-cloud-instance": instance_id,
        "x-ynput-cloud-key": request.key,
    }

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        res = await client.get(
            f"{ayonconfig.ynput_cloud_api_url}/api/v1/me",
            headers=headers,
        )
        if res.status_code != 200:
            raise ForbiddenException("Invalid Ynput cloud key")
        data = res.json()

    await Postgres.execute(
        """
        INSERT INTO secrets (name, value)
        VALUES ('ynput_cloud_key', $1)
        ON CONFLICT (name) DO UPDATE SET value = $1
        """,
        request.key,
    )

    return YnputConnectResponseModel(**data)


@router.delete("")
async def delete_ynput_cloud_key(user: CurrentUser) -> EmptyResponse:
    """Remove the Ynput cloud key from the database"""
    if not user.is_admin:
        raise ForbiddenException("Only admins can remove the Ynput cloud key")

    await Postgres.execute("DELETE FROM secrets WHERE name = 'ynput_cloud_key'")
    return EmptyResponse()

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from ayon_server.api.dependencies import (
    CurrentUser,
    CurrentUserOptional,
    YnputConnectKey,
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

    user_name: str = Field(..., description="User name")
    user_email: str = Field(..., description="User email")


@router.get("")
async def get_ynput_connect_info(
    user: CurrentUser, ynput_connect_key: YnputConnectKey
) -> YnputConnectResponseModel:
    """
    Check whether the Ynput connect key is set and return the Ynput connect info
    """

    params = {"key": ynput_connect_key}

    # TODO: handle errors
    # TODO: cache this
    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        res = await client.get(
            f"{ayonconfig.ynput_connect_url}/api/connect/info", params=params
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
        user_name=data["userName"],
        user_email=data["userEmail"],
    )


@router.get("/authorize")
async def authorize_ynput_connect(origin_url: str = Query(...)):
    """Redirect to Ynput connect authorization page"""
    return RedirectResponse(
        f"{ayonconfig.ynput_connect_url}/api/connect?origin_url={origin_url}"
    )


@router.post("")
async def set_ynput_connect_key(
    request: YnputConnectRequestModel,
    user: CurrentUserOptional,
) -> EmptyResponse:
    """Store the Ynput connect key in the database and return the user info"""

    if user and not user.is_admin:
        raise ForbiddenException("Only admins can set the Ynput connect key")

    if user is None:
        has_admin = await admin_exists()
        if has_admin:
            raise ForbiddenException("Connecting to Ynput is allowed only on first run")

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        res = await client.get(
            f"{ayonconfig.ynput_connect_url}/api/connect/info?key={request.key}"
        )
        if res.status_code != 200:
            raise ForbiddenException("Invalid Ynput connect key")
        data = res.json()

    await Postgres.execute(
        """
        INSERT INTO secrets (name, value)
        VALUES ('ynput_connect_key', $1)
        ON CONFLICT (name) DO UPDATE SET value = $1
        """,
        request.key,
    )

    return YnputConnectResponseModel(
        user_name=data["userName"],
        user_email=data["userEmail"],
    )


@router.delete("")
async def delete_ynput_connect_key(user: CurrentUser) -> EmptyResponse:
    """Remove the Ynput connect key from the database"""
    if not user.is_admin:
        raise ForbiddenException("Only admins can remove the Ynput connect key")

    await Postgres.execute(
        """
        DELETE FROM secrets
        WHERE name = 'ynput_connect_key'
        """
    )

    return EmptyResponse()

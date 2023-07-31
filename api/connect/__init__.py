import httpx
from fastapi import APIRouter

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import BadRequestException, ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

router = APIRouter(
    prefix="/connect",
    tags=["YnputConnect"],
)


@router.get("")
async def get_ynput_connect_info(user: CurrentUser):
    """
    Check whether the Ynput connect key is set and return the Ynput connect info
    """
    res = await Postgres.fetch(
        """
        SELECT value FROM secrets
        WHERE name = 'ynput_connect_key'
        """
    )

    if not res:
        raise BadRequestException("Ynput connect key not found")

    key = res[0]["value"]

    # TODO: handle errors
    # TODO: cache this
    async with httpx.AsyncClient() as client:
        res = await client.get(f"https://auth.ayon.cloud/info?key={key}")

    return res.json()


class YnputConnectRequestModel(OPModel):
    key: str = Field(..., description="Ynput connect key")


@router.post("")
async def set_ynput_connect_key(
    request: YnputConnectRequestModel, user: CurrentUser
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can set the Ynput connect key")

    await Postgres.execute(
        """
        INSERT INTO secrets (name, value)
        VALUES ('ynput_connect_key', $1)
        ON CONFLICT (name) DO UPDATE SET value = $1
        """,
        request.key,
    )

    return EmptyResponse()


@router.delete("")
async def delete_ynput_connect_key(user: CurrentUser) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can set the Ynput connect key")
    await Postgres.execute(
        """
        DELETE FROM secrets
        WHERE name = 'ynput_connect_key'
        """
    )

    return EmptyResponse()

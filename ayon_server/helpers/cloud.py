import aiocache

from ayon_server.exceptions import AyonException, ForbiddenException
from ayon_server.lib.postgres import Postgres


@aiocache.cached()
async def get_instance_id() -> str:
    """Get the instance id"""

    res = await Postgres.fetch("SELECT value FROM config WHERE key = 'instanceId'")
    if not res:
        raise AyonException("instance id not set. This shouldn't happen.")
    return res[0]["value"]


@aiocache.cached()
async def get_ynput_cloud_key() -> str:
    """Get the Ynput Cloud key"""

    query = "SELECT value FROM secrets WHERE name = 'ynput_cloud_key'"
    res = await Postgres.fetch(query)
    if not res:
        raise ForbiddenException("Ayon is not connected to Ynput Cloud [ERR 1]")
    return res[0]["value"]


async def get_cloud_api_headers() -> dict[str, str]:
    """Get the headers for the market API"""

    instance_id = await get_instance_id()
    ynput_cloud_key = await get_ynput_cloud_key()

    headers = {
        "x-ynput-cloud-instance": instance_id,
        "x-ynput-cloud-key": ynput_cloud_key,
    }
    return headers

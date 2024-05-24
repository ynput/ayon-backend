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


@aiocache.cached()  # Cache for 1 hour
async def get_cloud_api_headers() -> dict[str, str]:
    """Get the headers for the market API"""
    try:
        instance_id = await get_instance_id()
    except Exception as e:
        raise e

    try:
        res = await Postgres.fetch(
            "SELECT value FROM secrets WHERE name = 'ynput_cloud_key'"
        )
        if not res:
            raise ForbiddenException("Ayon is not connected to Ynput Cloud [ERR 1]")
        ynput_cloud_key = res[0]["value"]
    except Exception as e:
        raise ForbiddenException(f"Failed to fetch cloud key: {str(e)}")

    headers = {
        "x-ynput-cloud-instance": instance_id,
        "x-ynput-cloud-key": ynput_cloud_key,
    }
    return headers

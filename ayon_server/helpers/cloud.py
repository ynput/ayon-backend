from ayon_server.exceptions import AyonException, ForbiddenException
from ayon_server.lib.postgres import Postgres

HEADERS: dict[str, str] = {}


async def get_cloud_api_headers() -> dict[str, str]:
    """Get the headers for the market API"""

    if HEADERS:
        return HEADERS

    res = await Postgres.fetch("SELECT value FROM config WHERE key = 'instanceId'")
    if not res:
        raise AyonException("instance id not set. This shouldn't happen.")
    instance_id = res[0]["value"]

    res = await Postgres.fetch(
        "SELECT value FROM secrets WHERE name = 'ynput_cloud_key'"
    )
    if not res:
        raise ForbiddenException("Ayon is not connected to Ynput Cloud [ERR 1]")
    ynput_cloud_key = res[0]["value"]
    HEADERS.update(
        {
            "x-ynput-cloud-instance": instance_id,
            "x-ynput-cloud-key": ynput_cloud_key,
        }
    )
    return HEADERS

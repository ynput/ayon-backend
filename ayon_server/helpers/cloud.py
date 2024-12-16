from typing import Any

from ayon_server.exceptions import AyonException, ForbiddenException
from ayon_server.lib.postgres import Postgres


class CloudUtils:
    instance_id: str | None = None
    cloud_key: str | None = None

    @classmethod
    async def get_instance_id(cls) -> str:
        """Get the instance id"""
        if cls.instance_id:
            return cls.instance_id

        res = await Postgres.fetch("SELECT value FROM config WHERE key = 'instanceId'")
        if not res:
            raise AyonException("instance id not set. This shouldn't happen.")
        cls.instance_id = res[0]["value"]
        assert cls.instance_id is not None
        return cls.instance_id

    @classmethod
    async def get_ynput_cloud_key(cls) -> str:
        """Get the Ynput Cloud key"""

        if cls.cloud_key:
            return cls.cloud_key

        query = "SELECT value FROM secrets WHERE name = 'ynput_cloud_key'"
        res = await Postgres.fetch(query)
        if not res:
            raise ForbiddenException("Ayon is not connected to Ynput Cloud [ERR 1]")

        cls.cloud_key = res[0]["value"]
        assert cls.cloud_key is not None
        return cls.cloud_key

    @classmethod
    async def get_api_headers(cls) -> dict[str, str]:
        instance_id = await cls.get_instance_id()
        ynput_cloud_key = await cls.get_ynput_cloud_key()

        headers = {
            "x-ynput-cloud-instance": instance_id,
            "x-ynput-cloud-key": ynput_cloud_key,
        }
        return headers

    @classmethod
    async def remove_ynput_cloud_key(cls) -> None:
        """Remove the Ynput Cloud key from cache"""
        query = "DELETE FROM secrets WHERE name = 'ynput_cloud_key'"
        await Postgres.execute(query)
        cls.cloud_key = None

    @classmethod
    async def get_licenses(cls, refresh: bool = False) -> list[dict[str, Any]]:
        _ = refresh  # TODO: use this to invalidate the cache
        result = []
        async for row in Postgres.iterate("SELECT id, data FROM licenses;"):
            lic = {"id": row["id"], **row["data"]}
            result.append(lic)
        return result

    @classmethod
    async def get_extras(cls) -> str:
        return ""  # TODO: implement this


#
# Deprecated functions. Kept for compatibility with old code.
#


async def get_instance_id() -> str:
    """Get the instance id.

    Deprecated, use CloudUtils.get_instance_id instead.
    """
    return await CloudUtils.get_instance_id()


async def get_ynput_cloud_key() -> str:
    """Get the Ynput Cloud key.

    Deprecated, use CloudUtils.get_ynput_cloud_key instead.
    """
    return await CloudUtils.get_ynput_cloud_key()


async def get_cloud_api_headers() -> dict[str, str]:
    """Get the headers for the market API"""
    return await CloudUtils.get_api_headers()


async def remove_ynput_cloud_key() -> None:
    """Remove the Ynput Cloud key from cache

    Deprecated, use CloudUtils.remove_ynput_cloud_key instead.
    """
    await CloudUtils.remove_ynput_cloud_key()

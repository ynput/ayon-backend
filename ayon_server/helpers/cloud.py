from typing import Annotated, Any

import httpx

from ayon_server.config import ayonconfig
from ayon_server.exceptions import AyonException, ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import Field, OPModel


class YnputCloudSubscriptionModel(OPModel):
    name: Annotated[str, Field(description="Name of the subscription")]
    product_type: Annotated[str, Field(description="Type of the subscription")]
    trial_end: Annotated[str | None, Field(description="End date of the trial")] = None


class YnputCloudInfoModel(OPModel):
    instance_id: Annotated[
        str,
        Field(
            description="Ynput cloud instance ID",
        ),
    ]
    instance_name: Annotated[
        str,
        Field(
            description="Name of the instance",
            example="ayon-staging",
        ),
    ]
    org_id: Annotated[
        str,
        Field(
            description="Organization ID",
        ),
    ]
    org_name: Annotated[
        str,
        Field(
            description="Name of the organization",
            example="Ynput",
        ),
    ]

    collect_saturated_metrics: Annotated[
        bool,
        Field(
            description="Collect saturated metrics",
        ),
    ] = False

    managed: Annotated[
        bool,
        Field(
            description="Is the instance managed by Ynput Cloud?",
        ),
    ] = False

    subscriptions: Annotated[
        list[YnputCloudSubscriptionModel],
        Field(
            default_factory=list,
            description="List of subscriptions",
        ),
    ]


class CloudUtils:
    instance_id: str | None = None
    cloud_key: str | None = None
    licenses_synced_at: float | None = None
    admin_exists: bool = False

    @classmethod
    async def get_admin_exists(cls) -> bool:
        if cls.admin_exists:
            return True
        query = "SELECT name FROM users WHERE data->>'isAdmin' = 'true'"
        if await Postgres.fetch(query):
            cls.admin_exists = True
            return True
        return False

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
    async def add_ynput_cloud_key(cls, key: str) -> None:
        await Postgres.execute(
            """
            INSERT INTO secrets (name, value)
            VALUES ('ynput_cloud_key', $1)
            ON CONFLICT (name) DO UPDATE SET value = $1
            """,
            key,
        )
        await cls.clear_cloud_info_cache()
        cls.cloud_key = key

    @classmethod
    async def remove_ynput_cloud_key(cls) -> None:
        """Remove the Ynput Cloud key from cache"""
        query = "DELETE FROM secrets WHERE name = 'ynput_cloud_key'"
        await Postgres.execute(query)
        await cls.clear_cloud_info_cache()
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

    @classmethod
    async def clear_cloud_info_cache(cls) -> None:
        await Redis.delete("global", "cloudinfo")

    @classmethod
    async def get_cloud_info(cls, force: bool = False) -> YnputCloudInfoModel:
        """Get the instance id."""
        try:
            instance_id = await cls.get_instance_id()
            ynput_cloud_key = await cls.get_ynput_cloud_key()
        except Exception:
            raise ForbiddenException("Not connected to ynput cloud")
        data = await Redis.get_json("global", "cloudinfo")
        if not data:
            return await cls.request_cloud_info(instance_id, ynput_cloud_key)
        return YnputCloudInfoModel(**data)

    @classmethod
    async def request_cloud_info(
        cls,
        instance_id: str,
        instance_key: str,
    ) -> YnputCloudInfoModel:
        headers = {
            "x-ynput-cloud-instance": instance_id,
            "x-ynput-cloud-key": instance_key,
        }
        async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
            res = await client.get(
                f"{ayonconfig.ynput_cloud_api_url}/api/v1/me",
                headers=headers,
            )
            if res.status_code in [401, 403]:
                await cls.remove_ynput_cloud_key()
                raise ForbiddenException("Invalid Ynput connect key")

            if res.status_code >= 400:
                raise ForbiddenException(
                    f"Unable to connect to Ynput Cloud. Server error {res.status_code}"
                )
            data = res.json()
            await Redis.set_json("global", "cloudinfo", data)
        return YnputCloudInfoModel(**data)


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

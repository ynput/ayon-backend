import time
from typing import Annotated, Any

import httpx

from ayon_server.config import ayonconfig
from ayon_server.exceptions import AyonException, ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.version import __version__


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
        str | None,
        Field(
            description="Name of the instance",
            example="ayon-staging",
        ),
    ] = None

    org_id: Annotated[
        str | None,
        Field(
            description="Organization ID",
        ),
    ] = None

    org_name: Annotated[
        str | None,
        Field(
            description="Name of the organization",
            example="Ynput",
        ),
    ] = None

    org_title: Annotated[
        str | None,
        Field(
            description="Name of the organization",
            example="Ynput",
            deprecated=True,
        ),
    ] = None

    managed: Annotated[
        bool,
        Field(
            description="Is the instance managed by Ynput Cloud?",
        ),
    ] = False

    collect_saturated_metrics: Annotated[
        bool,
        Field(
            description="Collect saturated metrics",
        ),
    ] = False

    subscriptions: Annotated[
        list[YnputCloudSubscriptionModel],
        Field(
            default_factory=list,
            description="List of subscriptions",
        ),
    ]

    connected: Annotated[
        bool,
        Field(
            description="Is the instance connected to Ynput Cloud?",
        ),
    ] = False


class CloudUtils:
    instance_id: str | None = None
    licenses_synced_at: float | None = None
    admin_exists: bool = False

    @classmethod
    async def get_admin_exists(cls) -> bool:
        if cls.admin_exists:
            return True
        query = "SELECT name FROM public.users WHERE data->>'isAdmin' = 'true'"
        if await Postgres.fetch(query):
            cls.admin_exists = True
            return True
        return False

    @classmethod
    async def get_instance_id(cls) -> str:
        """Get the instance id"""
        if cls.instance_id:
            return cls.instance_id

        query = "SELECT value FROM public.config WHERE key = 'instanceId'"
        res = await Postgres.fetchrow(query)
        if not res or (instance_id := res["value"]) is None:
            raise AyonException(
                "Instance id not set. This shouldn't happen. "
                "Your database may be corrupted, please run the setup."
            )
        cls.instance_id = instance_id
        return instance_id

    @classmethod
    async def get_ynput_cloud_key(cls) -> str:
        """Get the Ynput Cloud key"""
        ckey = await Redis.get("global", "ynput_cloud_key")

        if not ckey:
            query = "SELECT value FROM public.secrets WHERE name = 'ynput_cloud_key'"
            res = await Postgres.fetchrow(query)
            if not res:
                ckey = "none"
            else:
                ckey = res["value"]
            await Redis.set("global", "ynput_cloud_key", ckey)

        if str(ckey).lower() == "none":
            raise ForbiddenException("Ayon is not connected to Ynput Cloud [ERR 2]")

        return ckey

    @classmethod
    async def get_api_headers(cls) -> dict[str, str]:
        instance_id = await cls.get_instance_id()
        ynput_cloud_key = await cls.get_ynput_cloud_key()
        headers = {
            "x-ynput-cloud-instance": instance_id,
            "x-ynput-cloud-key": ynput_cloud_key,
            "x-ynput-server-version": __version__,
        }
        return headers

    @classmethod
    async def add_ynput_cloud_key(cls, key: str) -> None:
        await Postgres.execute(
            """
            INSERT INTO public.secrets (name, value)
            VALUES ('ynput_cloud_key', $1)
            ON CONFLICT (name) DO UPDATE SET value = $1
            """,
            key,
        )
        await cls.clear_cloud_info_cache()
        await Redis.set("global", "ynput_cloud_key", key)

    @classmethod
    async def remove_ynput_cloud_key(cls) -> None:
        """Remove the Ynput Cloud key from cache"""
        query = "DELETE FROM public.secrets WHERE name = 'ynput_cloud_key'"
        await Postgres.execute(query)
        await cls.clear_cloud_info_cache()
        await Redis.delete("global", "ynput_cloud_key")

    @classmethod
    async def get_licenses(cls, refresh: bool = False) -> list[dict[str, Any]]:
        _ = refresh  # TODO: use this to invalidate the cache
        result = []
        async for row in Postgres.iterate("SELECT id, data FROM public.licenses;"):
            lic = {"id": row["id"], **row["data"]}
            result.append(lic)
        return result

    @classmethod
    async def get_extras(cls) -> str:
        return ""  # TODO: implement this

    @classmethod
    async def clear_cloud_info_cache(cls) -> None:
        await Redis.delete("global", "ynput_cloud_key")
        await Redis.delete("global", "cloudinfo")

    @classmethod
    async def get_cloud_info(cls, force: bool = False) -> YnputCloudInfoModel:
        instance_id = await cls.get_instance_id()
        try:
            ynput_cloud_key = await cls.get_ynput_cloud_key()
        except Exception:
            return YnputCloudInfoModel(instance_id=instance_id, subscriptions=[])
        data = await Redis.get_json("global", "cloudinfo")
        if (not data) or data.get("fetched_at", 0) < time.time() - 600 or force:
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
            "x-ynput-server-version": __version__,
        }
        try:
            async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
                res = await client.get(
                    f"{ayonconfig.ynput_cloud_api_url}/api/v1/me",
                    headers=headers,
                )
                if res.status_code in [401, 403]:
                    await cls.remove_ynput_cloud_key()
                    raise ForbiddenException("Unable to connect to Ynput Cloud [ERR 0]")

                if res.status_code >= 400:
                    raise ForbiddenException(
                        f"Unable to connect to Ynput Cloud [ERR {res.status_code}]"
                    )
                data = res.json()
                if not isinstance(data, dict):
                    raise ValueError(f"Invalid response from Ynput Cloud: {res.text}")
                data["connected"] = True
        except Exception as e:
            logger.warning(f"Unable to connect to Ynput Cloud. Error: {e}")
            data = {
                "instance_id": instance_id,
                "connected": False,
            }

        data["fetched_at"] = time.time()
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

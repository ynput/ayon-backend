import asyncio

import httpx
from nxtools import log_traceback

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.config import ayonconfig
from ayon_server.lib.postgres import Postgres
from ayon_server.metrics import get_metrics


async def get_instance_id() -> str:
    res = await Postgres.fetch("SELECT value FROM config WHERE key = 'instanceId'")
    if not res:
        return ""
    return res[0]["value"]


async def get_ynput_cloud_key() -> str:
    res = await Postgres.fetch(
        "SELECT value FROM secrets WHERE name = 'ynput_cloud_key'"
    )
    if not res:
        return ""
    return res[0]["value"]


async def post_metrics(instance_id: str):
    yc_key = await get_ynput_cloud_key()
    assert instance_id, "Instance ID is not set"

    headers = {
        "x-ynput-cloud-instance": instance_id,
        "x-ynput-cloud-key": yc_key,
    }

    metrics = await get_metrics()
    payload = metrics.dict(exclude_none=True)

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        res = await client.post(
            f"{ayonconfig.ynput_cloud_api_url}/api/v1/metrics",
            json=payload,
            headers=headers,
        )

    res.raise_for_status()


class MetricsCollector(BackgroundWorker):
    """Background task for collecting metrics"""

    async def run(self):
        # this won't change during the lifetime of the server
        instance_id = await get_instance_id()
        has_error = False

        while True:
            # let the server catch a breath
            await asyncio.sleep(60)

            try:
                await post_metrics(instance_id)

            except AssertionError:
                # server is not set up to send metrics, try again in an hour,
                # but be quiet about it
                await asyncio.sleep(3600)
                continue

            except Exception:
                # if something goes wrong, try again in an hour
                if not has_error:
                    # log the error only once
                    log_traceback("Failed to send metrics")
                    has_error = True
                await asyncio.sleep(3600)
                continue
            else:
                has_error = False

            # otherwise, wait for 6 hours
            await asyncio.sleep(3600 * 6)


metrics_collector = MetricsCollector()

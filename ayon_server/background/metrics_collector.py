import asyncio

import httpx
from nxtools import log_traceback

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.config import ayonconfig
from ayon_server.helpers.cloud import get_cloud_api_headers
from ayon_server.metrics import get_metrics


async def post_metrics():
    try:
        headers = await get_cloud_api_headers()
    except Exception:
        # if we can't get the headers, we can't send metrics
        return

    metrics = await get_metrics()
    payload = metrics.dict(exclude_none=True)

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        res = await client.post(
            f"{ayonconfig.ynput_cloud_api_url}/api/v1/metrics",
            json=payload,
            headers=headers,
        )

    assert res.status_code != 401, "Invalid Ynput Cloud key"

    res.raise_for_status()


class MetricsCollector(BackgroundWorker):
    """Background task for collecting metrics"""

    async def run(self):
        # this won't change during the lifetime of the server
        has_error = False

        while True:
            # let the server catch a breath
            await asyncio.sleep(60)

            try:
                await post_metrics()
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

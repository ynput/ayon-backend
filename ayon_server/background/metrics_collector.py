import asyncio
import time

import httpx
from nxtools import logging

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.config import ayonconfig
from ayon_server.constraints import Constraints
from ayon_server.helpers.cloud import get_cloud_api_headers
from ayon_server.metrics import get_metrics


class MetricsCollector(BackgroundWorker):
    """Background task for collecting metrics"""

    last_collected: float = 0

    async def post_metrics(self):
        try:
            headers = await get_cloud_api_headers()
        except Exception:
            # if we can't get the headers, we can't send metrics
            return

        if not self.should_collect:
            return

        saturated = ayonconfig.metrics_send_saturated
        system = ayonconfig.metrics_send_system

        if not saturated:
            r = await Constraints.check("saturatedMetrics")
            if r:
                saturated = True
        if not system:
            r = await Constraints.check("systemMetrics")
            if r:
                system = True

        metrics = await get_metrics(saturated=saturated, system=system)
        payload = metrics.dict(exclude_none=True)

        async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
            res = await client.post(
                f"{ayonconfig.ynput_cloud_api_url}/api/v1/metrics",
                json=payload,
                headers=headers,
            )

        self.last_collected = time.time()
        assert res.status_code != 401, "Invalid Ynput Cloud key"

        res.raise_for_status()

    @property
    def should_collect(self) -> bool:
        if time.time() - self.last_collected > 3600:
            return True
        return False

    async def run(self):
        # this won't change during the lifetime of the server
        has_error = False

        while True:
            # let the server catch a breath
            await asyncio.sleep(60)

            try:
                await self.post_metrics()
            except AssertionError:
                # server is not set up to send metrics, try again in an hour,
                # but be quiet about it
                await asyncio.sleep(3600)
                continue

            except Exception:
                # if something goes wrong, try again in an hour
                if not has_error:
                    # log the problem only once
                    logging.warning("Failed to send metrics")
                    has_error = True
                await asyncio.sleep(3600)
                continue
            else:
                has_error = False

            # otherwise, wait for 6 hours
            await asyncio.sleep(3600 * 6)


metrics_collector = MetricsCollector()

"""Message bus connecting MCP tunnel hubs of all server workers.

A service's tunnel WebSocket is held by one worker of one server replica,
but an MCP request may land on any of them. Workers exchange tunnel
frames over the bus:

- ``tunnel channel`` - frames for a tunnel, published by any worker and
  read by the worker holding the tunnel.
- ``worker channel`` - response frames for requests a worker is serving.

Connected tunnels are announced with an expiry, so a crashed worker's
tunnels disappear after ``TUNNEL_TTL`` seconds.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from redis.asyncio.client import PubSub

from ayon_server.lib.redis import Redis
from ayon_server.logging import log_traceback

# How long an announced tunnel stays listed without a heartbeat.
TUNNEL_TTL = 30

MessageHandler = Callable[[str, bytes], Awaitable[None]]

# -- -- --==============---=----- . .
#
#        _/_|[][][][][] | - -
#       (    Tunnel Bus | - -
#       =--OO-------OO--= - -
# ------===============-------- .. .

class TunnelBus(ABC):
    """Transport between the tunnel hubs of all workers."""

    @abstractmethod
    async def start(self, handler: MessageHandler) -> None:
        """Start delivering messages of subscribed channels to ``handler``.

        ``handler`` is called with the channel name and the message, one
        message at a time, in the order they were published.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop delivering messages."""

    @abstractmethod
    async def subscribe(self, channel: str) -> None:
        """Start receiving messages published to ``channel``.

        Args:
            channel: The name of the channel to subscribe to.

        """

    @abstractmethod
    async def unsubscribe(self, channel: str) -> None:
        """Stop receiving messages published to ``channel``.

        Args:
            channel: The name of the channel to unsubscribe from.

        """

    @abstractmethod
    async def publish(self, channel: str, message: bytes) -> int:
        """Send ``message`` to the subscribers of ``channel``.

        Args:
            channel: The name of the channel to publish the message to.
            message: The message to send to the subscribers of the channel.

        Returns:
            The number of subscribers that received the message.

        """

    @abstractmethod
    async def announce(self, tunnel_id: str) -> None:
        """List a connected tunnel for ``TUNNEL_TTL`` seconds.

        Args:
            tunnel_id: The ID of the tunnel to announce.

        """

    @abstractmethod
    async def withdraw(self, tunnel_id: str) -> None:
        """Remove a tunnel from the list.

        Args:
            tunnel_id: The ID of the tunnel to remove from the list.

        """

    @abstractmethod
    async def tunnels(self) -> list[str]:
        """Return the ids of all listed tunnels.

        Returns:
            A list of tunnel IDs that are currently listed.

        """


class RedisTunnelBus(TunnelBus):
    """Tunnel bus on Redis pub/sub, with tunnels listed in a sorted set."""

    def __init__(self) -> None:
        self._pubsub: PubSub | None = None
        self._task: asyncio.Task[None] | None = None
        self._handler: MessageHandler | None = None

    def _name(self, name: str) -> str:
        return f"{Redis.prefix}mcp-{name}"

    async def start(self, handler: MessageHandler) -> None:
        self._handler = handler
        self._pubsub = await Redis.pubsub()
        self._task = asyncio.create_task(self._read())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._pubsub is not None:
            await self._pubsub.aclose()
            self._pubsub = None

    async def subscribe(self, channel: str) -> None:
        assert self._pubsub is not None, "bus not started"
        await self._pubsub.subscribe(self._name(channel))

    async def unsubscribe(self, channel: str) -> None:
        if self._pubsub is not None:
            await self._pubsub.unsubscribe(self._name(channel))

    async def publish(self, channel: str, message: bytes) -> int:
        if not Redis.connected:
            await Redis.connect()
        return await Redis.redis_pool.publish(self._name(channel), message)

    async def announce(self, tunnel_id: str) -> None:
        if not Redis.connected:
            await Redis.connect()
        await Redis.redis_pool.zadd(
            self._name("tunnels"), {tunnel_id: time.time() + TUNNEL_TTL}
        )

    async def withdraw(self, tunnel_id: str) -> None:
        if not Redis.connected:
            await Redis.connect()
        await Redis.redis_pool.zrem(self._name("tunnels"), tunnel_id)

    async def tunnels(self) -> list[str]:
        if not Redis.connected:
            await Redis.connect()
        key = self._name("tunnels")
        now = time.time()
        await Redis.redis_pool.zremrangebyscore(key, "-inf", now)
        members = await Redis.redis_pool.zrangebyscore(key, now, "+inf")
        return [m.decode() if isinstance(m, bytes) else str(m) for m in members]

    async def _read(self) -> None:
        assert self._pubsub is not None
        prefix = self._name("")
        while True:
            if not self._pubsub.subscribed:
                # get_message fails until the first subscription
                await asyncio.sleep(0.1)
                continue
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                log_traceback("MCP tunnel bus read failed")
                await asyncio.sleep(1)
                continue
            if message is None or self._handler is None:
                continue
            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode()
            try:
                await self._handler(channel.removeprefix(prefix), message["data"])
            except Exception:
                log_traceback("MCP tunnel bus handler failed")

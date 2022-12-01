import asyncio
import time
import uuid
from contextlib import suppress
from typing import Any

from fastapi.websockets import WebSocket, WebSocketDisconnect
from nxtools import log_traceback, logging

from openpype.api.system import restart_server
from openpype.auth.session import Session
from openpype.background import BackgroundTask
from openpype.config import pypeconfig
from openpype.lib.redis import Redis
from openpype.utils import json_dumps, json_loads

ALWAYS_SUBSCRIBE = [
    "server.started",
    "server.restart_requested",
]


class Client:
    def __init__(self, sock: WebSocket):
        self.id = str(uuid.uuid1())
        self.sock: WebSocket = sock
        self.topics: list[str] = []
        self.disconnected = False
        self.authorized = False
        self.created_at = time.time()
        self.user = None

    @property
    def user_name(self) -> str | None:
        if self.user is None:
            return None
        return self.user.name

    async def authorize(self, access_token: str, topics: list[str]) -> bool:
        session_data = await Session.check(access_token, None)
        if session_data:
            self.topics = [*topics, *ALWAYS_SUBSCRIBE] if "*" not in topics else ["*"]
            self.authorized = True
            self.user = session_data.user
            # logging.info(
            #     "Authorized connection",
            #     session_data.user.name,
            #     "topics:",
            #     self.topics,
            # )
            return True
        return False

    async def send(self, message: dict[str, Any], auth_only: bool = True):
        if (not self.authorized) and auth_only:
            return None
        if not self.is_valid:
            return None
        try:
            await self.sock.send_text(json_dumps(message))
        except WebSocketDisconnect:
            self.disconnected = True

    async def receive(self):
        data = await self.sock.receive_text()
        try:
            message = json_loads(data)
            assert type(message) is dict
            assert "topic" in message
        except AssertionError:
            return None
        except Exception:
            log_traceback()
            return None
        return message

    @property
    def is_valid(self) -> bool:
        if self.disconnected:
            return False
        if not self.authorized and (time.time() - self.created_at > 3):
            # logging.info("Removing unauthorized client")
            return False
        return True


class Messaging(BackgroundTask):
    def initialize(self):
        self.clients: dict[str, Client] = {}

    async def join(self, websocket: WebSocket):
        if not self.is_running:
            await websocket.reject()
            return
        await websocket.accept()
        client = Client(websocket)
        self.clients[client.id] = client
        return client

    async def purge(self):
        to_rm = []
        for client_id, client in list(self.clients.items()):
            if not client.is_valid:
                if not client.disconnected:
                    await client.sock.close(code=1000)
                to_rm.append(client_id)
        for client_id in to_rm:
            with suppress(KeyError):
                del self.clients[client_id]

    async def run(self) -> None:
        self.pubsub = await Redis.pubsub()
        await self.pubsub.subscribe(pypeconfig.redis_channel)
        last_msg = time.time()

        while True:
            try:
                raw_message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=2,
                )
                if raw_message is None:
                    await asyncio.sleep(0.01)
                    if time.time() - last_msg > 5:
                        message = {"topic": "heartbeat"}
                        last_msg = time.time()
                    else:
                        continue
                else:
                    message = json_loads(raw_message["data"])

                for client_id, client in self.clients.items():
                    for topic in client.topics:
                        if topic == "*" or message["topic"].startswith(topic):
                            await client.send(message)
                            break

                if message["topic"] == "server.restart_requested":
                    restart_server()

                await self.purge()

            except Exception:
                log_traceback(handlers=None)
                await asyncio.sleep(0.5)

        logging.warning("Stopping redis2ws")

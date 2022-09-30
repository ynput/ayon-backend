import asyncio
import time
import uuid
from contextlib import suppress
from typing import Any

from fastapi.websockets import WebSocket, WebSocketDisconnect
from nxtools import log_traceback, logging

from openpype.api.system import restart_server
from openpype.auth.session import Session
from openpype.config import pypeconfig
from openpype.lib.redis import Redis
from openpype.utils import json_dumps, json_loads

ALWAYS_SUBSCRIBE = [
    "server.started",
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
            logging.info(
                "Authorized connection",
                session_data.user.name,
                "topics:",
                self.topics,
            )
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
            logging.info("Removing unauthorized client")
            return False
        return True


class Messaging:
    def __init__(self) -> None:
        self.clients: dict[str, Client] = {}
        self.started = False

    async def join(self, websocket: WebSocket):
        await websocket.accept()
        client = Client(websocket)
        self.clients[client.id] = client
        if not self.started:
            await self.start()
        return client

    async def start(self) -> None:
        self.pubsub = await Redis.pubsub()
        await self.pubsub.subscribe(pypeconfig.redis_channel)
        asyncio.create_task(self.listen())

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

    async def listen(self) -> None:
        logging.info("Starting redis2ws")
        self.started = True
        last_msg = time.time()
        while True:
            try:
                raw_message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True
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

                if message["topic"] == "server.restart_requested":
                    logging.warning("Server configuration changed. Requesting restart.")
                    await restart_server()

                for client_id, client in self.clients.items():
                    for topic in client.topics:
                        if topic == "*" or message["topic"].startswith(topic):
                            await client.send(message)
                            break

                await self.purge()

            except Exception:
                log_traceback()
                await asyncio.sleep(0.5)

        logging.warning("Stopping redis2ws")
        self.started = False

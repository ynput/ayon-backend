import asyncio
import copy
import time
import uuid
from contextlib import suppress
from typing import Any

from fastapi.websockets import WebSocket, WebSocketDisconnect

from ayon_server.api.system import restart_server
from ayon_server.auth.session import Session
from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity
from ayon_server.events import EventStream, HandlerType
from ayon_server.exceptions import UnauthorizedException
from ayon_server.lib.redis import Redis
from ayon_server.logging import log_traceback, logger
from ayon_server.utils import json_dumps, json_loads

ALWAYS_SUBSCRIBE = (
    "server.started",
    "server.restart_requested",
    "heartbeat",
)

GUEST_TOPICS = (
    "activity.created",
    "heartbeat",
    "activity.updated",
    "entity.version.updated",
)


async def _handle_subscribers_task(event_id: str, handlers: list[HandlerType]) -> None:
    try:
        event = await EventStream.get(event_id)
    except Exception:
        logger.error(f"Failed to fetch event '{event_id}' for global handlers")
        return
    for handler in handlers:
        try:
            await handler(event)
        except Exception:
            log_traceback(f"Error in global event handler '{handler.__name__}'")


async def handle_subscribers(message: dict[str, Any]) -> None:
    event_id = message.get("id", None)
    store = message.get("store", None)
    topic = message.get("topic", None)
    if not (event_id and store and topic):
        return

    handlers = EventStream.global_hooks.get(topic, {}).values()
    if not handlers:
        return
    asyncio.create_task(_handle_subscribers_task(event_id, list(handlers)))


class Client:
    id: str
    sock: WebSocket
    topics: list[str] = []
    disconnected: bool = False
    authorized: bool = False
    created_at: float
    project_name: str | None = None
    user: UserEntity | None = None

    def __init__(self, sock: WebSocket):
        self.id = str(uuid.uuid1())
        self.sock: WebSocket = sock
        self.created_at = time.time()

    @property
    def user_name(self) -> str | None:
        if self.user is None:
            return None
        return self.user.name

    @property
    def is_guest(self) -> bool:
        if self.user is None:
            # This should never happen, but just in case and to make mypy happy
            return True
        return self.user.data.get("isGuest", False)

    async def authorize(
        self,
        access_token: str,
        topics: list[str],
        project: str | None = None,
    ) -> bool:
        try:
            session_data = await Session.check(access_token, None)
        except UnauthorizedException as e:
            logger.warning(f"[WS] Unauthorized access: {e}")
            session_data = None
        if session_data is not None:
            self.topics = [*topics, *ALWAYS_SUBSCRIBE] if "*" not in topics else ["*"]
            self.authorized = True
            self.user = session_data.user_entity
            self.project_name = project
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
            logger.warning("[WS] Client disconnected")
            self.disconnected = True
        except RuntimeError:
            logger.warning("[WS] Client disconnected (RTE)")
            self.disconnected = True
        except Exception:
            log_traceback("[WS] Error sending message")

    async def receive(self):
        data = await self.sock.receive_text()
        try:
            message = json_loads(data)
            assert isinstance(message, dict)
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
            logger.trace(f"[WS] Disconnected client: {self}")
            return False
        if not self.authorized and (time.time() - self.created_at > 3):
            logger.trace(f"[WS] Unauthorized client timed out: {self}")
            return False
        return True

    def __repr__(self) -> str:
        return f"<WSClient user={self.user_name}>"


class Messaging(BackgroundWorker):
    def initialize(self):
        self.clients: dict[str, Client] = {}

    async def join(self, websocket: WebSocket):
        if not self.is_running:
            await websocket.close()
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
                    with suppress(RuntimeError):
                        await client.sock.close(code=1000)
                to_rm.append(client_id)
        for client_id in to_rm:
            with suppress(KeyError):
                del self.clients[client_id]

    async def run(self) -> None:
        self.pubsub = await Redis.pubsub()
        await self.pubsub.subscribe(ayonconfig.redis_channel)
        self.last_msg = time.time()

        while True:
            try:
                await self.main()
            except Exception:
                log_traceback("Unhandled exception in messaging loop", nodb=True)
                await asyncio.sleep(0.5)

    async def main(self) -> None:
        """Main messaging loop

        Waits for messages from Redis and sends them to connected WebSocket clients.
        """

        raw_message = await self.pubsub.get_message(
            ignore_subscribe_messages=True,
            timeout=2,
        )
        if raw_message is None:
            await asyncio.sleep(0.01)
            if time.time() - self.last_msg > 5:
                message = {"topic": "heartbeat"}
                self.last_msg = time.time()
            else:
                return
        else:
            message = json_loads(raw_message["data"])

        await handle_subscribers(message)

        topic = message.get("topic", None)
        if topic is None:
            logger.trace(f"WS Message without topic: {message}")
            return

        #
        # Send the message to all connected clients
        # (or only to those subscribed to the topic and authorized)
        #

        for client in self.clients.values():
            project_name = message.get("project", None)
            if project_name is not None:
                if topic == "inbox.message" or topic in ALWAYS_SUBSCRIBE:
                    # inbox messages are sent to all projects
                    pass

                elif client.project_name and client.project_name != project_name:
                    # only send project-specific messages to clients
                    continue

                if client.user:
                    if client.user.is_guest:
                        if topic not in GUEST_TOPICS:
                            continue

                    elif not client.user.is_manager:
                        access_groups = client.user.data.get("accessGroups", {})
                        if project_name not in access_groups:
                            continue

            # Does the message have explicit recipients?
            # If so, only send to those recipients

            recipients = message.get("recipients", None)
            if isinstance(recipients, list):
                if client.user_name not in recipients:
                    continue

            if topic not in ALWAYS_SUBSCRIBE:
                for client_topic in client.topics:
                    if client_topic == "*":
                        break

                    elif topic.startswith(client_topic):
                        break
                else:
                    # Client is not subscribed to this topic
                    # Skip sending
                    continue

            # Message is good to be sent to this client
            # we just remove the recipients field if present
            # as it's not needed anymore

            m = copy.deepcopy(message)
            m.pop("recipients", None)
            await client.send(m)

        # Special handling for some topics
        # These are server-wide actions that need to be executed

        if topic == "server.restart_requested":
            restart_server()

        await self.purge()


messaging = Messaging()

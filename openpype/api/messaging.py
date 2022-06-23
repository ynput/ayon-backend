import asyncio

from fastapi.websockets import WebSocket, WebSocketDisconnect
from nxtools import log_traceback, logging

from openpype.config import pypeconfig
from openpype.lib.redis import Redis


class Messaging:
    def __init__(self) -> None:
        self.connections: list[WebSocket] = []
        self.started = False

    async def join(self, websocket: WebSocket):
        if not self.started:
            logging.info("Starting listener")
            await self.start()

        await websocket.accept()
        self.connections.append(websocket)

    async def leave(self, websocket: WebSocket):
        self.connections.remove(websocket)

    async def send(self, message: str):
        if not self.started:
            await self.start()
        await Redis.publish(message)

    async def start(self) -> None:
        self.pubsub = await Redis.pubsub()
        await self.pubsub.subscribe(pypeconfig.redis_channel)
        asyncio.create_task(self.listen())
        self.started = True

    async def listen(self) -> None:
        while self.connections:
            try:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if message is None:
                    await asyncio.sleep(0.01)
                    continue
                remove_list = []
                for ws in self.connections:
                    try:
                        await ws.send_text(f"GOT MESSAGE {message}")
                    except WebSocketDisconnect:
                        remove_list.append(ws)
                for ws in remove_list:
                    self.leave(ws)
            except Exception:
                log_traceback()

        logging.warning("Stopping redis2ws")
        self.started = False

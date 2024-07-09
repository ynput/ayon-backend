import asyncio
import os
import re
import signal
from typing import Any, Awaitable, Callable


class AsyncFFmpeg:
    re_position = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})", re.U | re.I)
    process: asyncio.subprocess.Process | None

    def __init__(self, *args: Any) -> None:
        self.args = ["ffmpeg", "-y", "-v", "quiet", "-stats"]
        for arg in args:
            self.args.append(str(arg))
        self.process = None

    @staticmethod
    def time2sec(search: re.Match[Any]) -> float:
        hh, mm, ss, cs = (
            search.group(1),
            search.group(2),
            search.group(3),
            search.group(4),
        )
        return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(cs) / 100.0

    async def start(self, progress_handler: Callable[[float], Awaitable[None]]) -> None:
        self.process = await asyncio.create_subprocess_exec(
            *self.args, stderr=asyncio.subprocess.PIPE
        )

        asyncio.create_task(self._handle_stderr(self.process.stderr, progress_handler))

    async def _handle_stderr(
        self, stderr, progress_handler: Callable[[float], Awaitable[None]]
    ) -> None:
        buffer = ""
        while True:
            # we can do this, because ffmpeg only outputs stats,
            # so every byte is a character
            chunk = await stderr.read(1)
            if not chunk:
                break
            chunk = chunk.decode("utf-8")
            if chunk == "\r":
                if buffer:
                    search = self.re_position.search(buffer)
                    if search:
                        current_time = self.time2sec(search)
                        progress_handler(current_time)
                    buffer = ""
            else:
                buffer += chunk

    async def stop(self):
        if self.process and self.process.returncode is None:
            print("Stopping ffmpeg process")
            os.kill(self.process.pid, signal.SIGTERM)
            await self.process.communicate()
            self.process = None

    async def wait(self):
        if self.process:
            await self.process.wait()

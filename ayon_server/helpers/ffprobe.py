import asyncio
import json
from typing import Any


async def ffprobe(file_path: str) -> dict[str, Any]:
    """Runs ffprobe on a file and returns the metadata."""
    process = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        file_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise Exception(f"ffprobe failed: {stderr.decode()}")

    return json.loads(stdout)

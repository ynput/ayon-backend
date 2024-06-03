import os

import aiofiles
from fastapi import Request, Response, status

from ayon_server.exceptions import (
    NotFoundException,
    RangeNotSatisfiableException,
)


class VideoResponse(Response):
    content_type = "video/mp4"


async def get_bytes_range(file_name: str, start: int, end: int) -> bytes:
    """Get a range of bytes from a file"""
    async with aiofiles.open(file_name, mode="rb") as f:
        await f.seek(start)
        pos = start
        read_size = end - pos + 1
        return await f.read(read_size)


def _get_range_header(range_header: str, file_size: int) -> tuple[int, int]:
    try:
        h = range_header.replace("bytes=", "").split("-")
        start = int(h[0]) if h[0] != "" else 0
        end = int(h[1]) if h[1] != "" else file_size - 1
    except ValueError as e:
        raise RangeNotSatisfiableException(str(e)) from e

    if start > end or start < 0 or end > file_size - 1:
        raise RangeNotSatisfiableException(f"Invalid range: {start}-{end}")
    return start, end


async def range_requests_response(
    request: Request,
    file_path: str,
    content_type: str,
) -> VideoResponse:
    """Handle range requests for video files."""

    file_size = os.stat(file_path).st_size
    max_chunk_size = 1024 * 1024
    range_header = request.headers.get("range")

    # screw firefox
    if ua := request.headers.get("user-agent"):
        if "firefox" in ua.lower():
            max_chunk_size = file_size

    headers = {
        "content-type": content_type,
        "accept-ranges": "bytes",
        "content-encoding": "identity",
        "content-length": str(file_size),
        "access-control-expose-headers": (
            "content-type, accept-ranges, content-length, "
            "content-range, content-encoding"
        ),
    }
    start = 0
    end = file_size - 1
    status_code = status.HTTP_200_OK

    if range_header is not None:
        start, end = _get_range_header(range_header, file_size)
        end = min(end, start + max_chunk_size - 1, file_size - 1)

        size = end - start + 1
        headers["content-length"] = str(size)
        headers["content-range"] = f"bytes {start}-{end}/{file_size}"
        status_code = status.HTTP_206_PARTIAL_CONTENT

    payload = await get_bytes_range(file_path, start, end)

    return VideoResponse(
        content=payload,
        headers=headers,
        status_code=status_code,
    )


async def serve_video(request: Request, video_path: str) -> VideoResponse:
    if not os.path.exists(video_path):
        raise NotFoundException("Video not found")

    return await range_requests_response(request, video_path, "video/mp4")

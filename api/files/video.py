# This is a monument to the previous implementation. It is no longer used,
# but it is kept here for reference. The new implementation uses native starlette
# FileResponse, that covers range requests and streaming out of the box.

import os
from collections.abc import AsyncIterable

import aiofiles
from fastapi import Request, status
from fastapi.responses import StreamingResponse

from ayon_server.exceptions import (
    NotFoundException,
    RangeNotSatisfiableException,
)


def get_file_size(file_name: str) -> int:
    """Get the size of a file"""
    if not os.path.exists(file_name):
        raise NotFoundException("File not found")
    return os.stat(file_name).st_size


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


async def stream_video(
    file_path: str,
    start: int,
    end: int,
    *,
    request: Request,
) -> AsyncIterable[bytes]:
    async with aiofiles.open(file_path, mode="rb") as f:
        await f.seek(start)
        pos = start
        read_size = end - pos + 1
        while read_size > 0:
            if await request.is_disconnected():
                break
            chunk_size = min(1024 * 1024, read_size)  # Read in 1MB chunks
            data = await f.read(chunk_size)
            if not data:
                break
            yield data
            pos += len(data)
            read_size -= len(data)


async def range_requests_response(
    request: Request,
    file_path: str,
    content_type: str,
) -> StreamingResponse:
    """Handle range requests for video files."""

    file_size = get_file_size(file_path)
    range_header = request.headers.get("range")

    headers = {
        "content-type": content_type,
        "content-length": str(file_size),
        "accept-ranges": "bytes",
        "access-control-expose-headers": (
            "content-type, accept-ranges, content-length, "
            "content-range, content-encoding"
        ),
    }

    start = 0
    end = file_size - 1

    if range_header is not None:
        start, end = _get_range_header(range_header, file_size)
        status_code = status.HTTP_206_PARTIAL_CONTENT
    else:
        start = 0
        end = file_size - 1
        status_code = status.HTTP_200_OK

    size = end - start + 1

    if status_code == status.HTTP_200_OK:
        headers["cache-control"] = "private, max-age=600"

    headers["content-length"] = str(size)
    headers["content-range"] = f"bytes {start}-{end}/{file_size}"

    return StreamingResponse(
        stream_video(file_path, start, end, request=request),
        status_code=status_code,
        headers=headers,
    )


async def serve_video(
    request: Request,
    video_path: str,
    content_type: str,
) -> StreamingResponse:
    if not os.path.exists(video_path):
        raise NotFoundException("Video not found")

    return await range_requests_response(request, video_path, content_type)

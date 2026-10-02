"""Forward HTTP requests to the MCP service and stream responses back."""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .hub import Route, TunnelClosedError, TunnelHub
from .protocol import USER_HEADER, Frame, FrameType, chunks, filter_headers

# Path of the streamable HTTP endpoint inside the service's app.
SERVICE_MCP_PATH = "/mcp"

# How long to wait for the service to start answering a request.
RESPONSE_START_TIMEOUT = 60.0

# Caller credentials never reach the service. The server authenticates the
# caller and passes only the user name (``USER_HEADER``); the service calls
# AYON with its own service key and ``x-as-user``. A client-sent
# ``USER_HEADER`` is dropped, so it can't be used to impersonate anyone.
CREDENTIAL_HEADERS = frozenset(
    {"authorization", "cookie", "x-api-key", "x-as-user", USER_HEADER}
)

# The service must not set cookies on the AYON server origin.
BLOCKED_RESPONSE_HEADERS = frozenset({"set-cookie"})


def _error(status: int, detail: str) -> Response:
    return JSONResponse({"detail": detail}, status_code=status)


def _unavailable() -> Response:
    response = _error(503, "MCP service is not connected")
    response.headers["Retry-After"] = "5"
    return response


class _ProxiedRequest:
    """One HTTP request forwarded through a tunnel."""

    def __init__(self, route: Route) -> None:
        self.route = route
        self.finished = False

    async def forward(self, request: Request, user_name: str) -> None:
        """Send the request line, headers and body to the service."""
        headers = filter_headers(list(request.headers.items()), drop=CREDENTIAL_HEADERS)
        headers.append((USER_HEADER, user_name))
        stream_id = self.route.stream_id
        await self.route.send(
            Frame.with_json(
                FrameType.REQUEST_START,
                stream_id,
                {
                    "method": request.method,
                    "path": SERVICE_MCP_PATH,
                    "query": request.url.query,
                    "headers": headers,
                },
            )
        )
        async for body in request.stream():
            for chunk in chunks(body):
                await self.route.send(Frame(FrameType.REQUEST_BODY, stream_id, chunk))
        await self.route.send(Frame(FrameType.REQUEST_END, stream_id))

    async def cancel(self) -> None:
        """Close the route and tell the service, unless the response finished."""
        self.route.close()
        if not self.finished:
            with contextlib.suppress(Exception):
                await self.route.send(Frame(FrameType.CANCEL, self.route.stream_id))

    async def respond(self, first: Frame | None) -> Response:
        """Turn the service's first frame into the client response."""
        if first is None:
            self.route.close()
            return _error(502, "MCP service disconnected")
        if first.type is FrameType.RESPONSE_ERROR:
            self.route.close()
            message = first.json().get("message", "unknown error")
            return _error(502, f"MCP service error: {message}")
        if first.type is not FrameType.RESPONSE_START:
            await self.cancel()
            return _error(502, f"Unexpected MCP tunnel frame {first.type.name}")

        start = first.json()
        response = StreamingResponse(
            self._body(), status_code=int(start.get("status", 502))
        )
        for name, value in filter_headers(
            [(str(h[0]), str(h[1])) for h in start.get("headers", [])],
            drop=BLOCKED_RESPONSE_HEADERS,
        ):
            response.headers.append(name, value)
        # Keep reverse proxies (nginx, ingress) from buffering SSE streams.
        response.headers["X-Accel-Buffering"] = "no"
        return response

    async def _body(self) -> AsyncIterator[bytes]:
        try:
            while True:
                frame = await self.route.receive()
                if frame is None or frame.type in {
                    FrameType.RESPONSE_END,
                    FrameType.RESPONSE_ERROR,
                }:
                    # The status is already sent; on error the client
                    # sees a truncated body.
                    self.finished = True
                    return
                if frame.type is FrameType.RESPONSE_BODY:
                    yield frame.payload
        finally:
            # Runs on completion and when the client disconnects
            # mid-stream; only the latter sends CANCEL.
            await self.cancel()


async def proxy_request(request: Request, hub: TunnelHub, user_name: str) -> Response:
    """Forward an MCP HTTP request to a connected service.

    ``request`` must already be authenticated as ``user_name``. The service
    acts on AYON as that user (service API key + ``x-as-user``).

    Returns the service's response, streamed as it is produced, or
    502/503/504 if the tunnel fails.
    """
    route = await hub.open_route()
    if route is None:
        return _unavailable()

    proxied = _ProxiedRequest(route)
    try:
        await proxied.forward(request, user_name)
        first = await asyncio.wait_for(route.receive(), timeout=RESPONSE_START_TIMEOUT)
    except TunnelClosedError:
        route.close()
        return _error(502, "MCP service disconnected")
    except TimeoutError:
        await proxied.cancel()
        return _error(504, "MCP service did not respond")
    except BaseException:
        # The client went away while the request was being forwarded.
        await proxied.cancel()
        raise
    return await proxied.respond(first)

"""MCP endpoint, served by the MCP service through a WebSocket tunnel.

MCP clients (Claude, VS Code, ...) use ``/api/mcp`` with normal AYON
authentication. The MCP service connects to ``/api/mcp/ws`` and answers
the requests, so it needs no listening port, public IP or ingress.

Both endpoints are left out of the OpenAPI schema: they carry the MCP
protocol rather than a REST API, and ayon-mcp generates its tools from
the schema.
"""

__all__ = ["router"]

from fastapi import APIRouter, Request, Response, WebSocket

from ayon_server.api.auth import user_from_request
from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import AyonException
from ayon_server.logging import logger
from ayon_server.mcp import mcp_tunnels, proxy_request
from ayon_server.mcp.protocol import PROTOCOL_HEADER, PROTOCOL_VERSION

router = APIRouter(prefix="/mcp", tags=["MCP"], include_in_schema=False)

# Close codes for rejected tunnels. The WebSocket is accepted first and then
# closed with one of these and a reason, so the service can log what is
# wrong. (A rejection before accepting reaches clients as a bare HTTP 403,
# which is also what servers without this endpoint send.)
CLOSE_UNSUPPORTED = 4400
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403


async def _reject(websocket: WebSocket, code: int, reason: str) -> None:
    await websocket.accept()
    await websocket.close(code=code, reason=reason)


@router.api_route("", methods=["GET", "POST", "DELETE"])
async def mcp_endpoint(request: Request, user: CurrentUser) -> Response:
    """MCP streamable HTTP endpoint, answered by the MCP service."""
    return await proxy_request(request, mcp_tunnels, user.name)


@router.websocket("/ws")
async def mcp_tunnel(websocket: WebSocket) -> None:
    """Tunnel connection of the MCP service.

    The HTTP auth middleware doesn't run for WebSockets, so the API key
    is checked here. Only service users may open a tunnel.
    """
    try:
        user = await user_from_request(websocket)  # type: ignore[arg-type]
    except AyonException as exc:
        await _reject(websocket, CLOSE_UNAUTHORIZED, f"Unauthorized: {exc}"[:120])
        return
    if not user.is_service:
        logger.warning(f"Rejecting MCP tunnel from non-service user {user.name}")
        await _reject(
            websocket,
            CLOSE_FORBIDDEN,
            f"User '{user.name}' is not a service user"[:120],
        )
        return

    version = websocket.headers.get(PROTOCOL_HEADER)
    if version != str(PROTOCOL_VERSION):
        logger.warning(
            f"Rejecting MCP tunnel from {user.name}: "
            f"protocol {version!r}, expected {PROTOCOL_VERSION}"
        )
        await _reject(
            websocket,
            CLOSE_UNSUPPORTED,
            f"Unsupported tunnel protocol {version!r}, "
            f"server supports {PROTOCOL_VERSION}"[:120],
        )
        return

    await websocket.accept()
    await mcp_tunnels.serve(websocket, user.name)

"""Stable endpoints of the authorization server addon.

Addon endpoints live under `/api/addons/{name}/{version}/`, so their
addresses change with every addon update. Applications store the address
of an authorization server and their registration with it, so it has to
stay the same: `/api/oauth/...` is handed to the authorization server of
the production bundle (see ayon_server.auth.authorization_server).

The request is passed on, not redirected: clients do not follow redirects
of token requests.

Not included in OpenAPI schema: it carries the OAuth protocol not REST API.
"""

__all__ = ["router"]

from fastapi import APIRouter, Request
from starlette.responses import Response

from ayon_server.auth.authorization_server import get_authorization_server
from ayon_server.exceptions import NotFoundException

router = APIRouter(prefix="/oauth", tags=["OAuth"], include_in_schema=False)


@router.api_route("/{path:path}", methods=["GET", "POST", "DELETE", "OPTIONS"])
async def authorization_server_endpoint(request: Request, path: str) -> Response:
    server = await get_authorization_server()
    if server is None:
        raise NotFoundException(f"API endpoint {request.url.path} not found")
    return await server.handle_request(request, path)

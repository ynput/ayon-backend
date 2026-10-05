"""Stable MCP endpoint for MCP clients.

The MCP addon serves MCP at ``/api/addons/mcp/{version}/mcp``. MCP clients
(Claude, VS Code, ...) are configured once, so ``/api/mcp`` redirects to
the MCP addon of the production bundle and keeps working across addon
updates. The addon does the rest, including the connection to the MCP
service.

Not included in OpenAPI schema: it carries the MCP protocol not REST API.
"""

__all__ = ["router"]

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ayon_server.addons.library import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import NotFoundException

MCP_ADDON_NAME = "mcp"

router = APIRouter(prefix="/mcp", tags=["MCP"], include_in_schema=False)


@router.api_route("", methods=["GET", "POST", "DELETE"])
async def mcp_endpoint(request: Request, user: CurrentUser) -> RedirectResponse:
    """Redirect to the MCP endpoint of the production MCP addon.

    307 keeps the method and body, so MCP clients follow it with POST.
    """
    try:
        addon = await AddonLibrary.getinstance().get_production_addon(MCP_ADDON_NAME)
    except KeyError:
        addon = None  # in the bundle, but not installed
    if addon is None:
        raise NotFoundException("MCP addon is not in the production bundle")
    url = f"/api/addons/{addon.name}/{addon.version}/mcp"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return RedirectResponse(url, status_code=307)

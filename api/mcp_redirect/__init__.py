"""Stable MCP endpoint for MCP clients.

The MCP addon serves MCP at ``/api/addons/mcp/{version}/mcp``. MCP clients
(Claude, VS Code, ...) are configured once, so ``/api/mcp`` redirects to
the MCP addon of the production bundle and keeps working across addon
updates. The addon does the rest, including the connection to the MCP
service.

Not included in OpenAPI schema: it carries the MCP protocol not REST API.
"""

__all__ = ["router"]

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from ayon_server.addons.library import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import NotFoundException

MCP_ADDON_NAME = "mcp"

router = APIRouter(prefix="/mcp", tags=["MCP"], include_in_schema=False)


@router.api_route("", methods=["GET", "POST", "DELETE"])
async def mcp_endpoint(
    request: Request,
    user: CurrentUser,
    variant: Annotated[str, Query(title="Variant")] = "production") -> RedirectResponse:
    """Redirect to the MCP endpoint of the production MCP addon.

    307 keeps the method and body, so MCP clients follow it with POST.

    Args:
        request: The incoming HTTP request.
        user: The current authenticated user.
        variant: The variant of the MCP addon to redirect to (default is "production").

    Returns:
        A RedirectResponse to the MCP endpoint of the specified addon variant.

    """
    try:
        addon = await AddonLibrary.getinstance().get_addon_by_variant(
            MCP_ADDON_NAME, variant=variant)
    except KeyError:
        addon = None
    if addon is None:
        msg = f"MCP addon ({MCP_ADDON_NAME}) with variant '{variant}' is not available"
        raise NotFoundException(msg)
    url = f"/api/addons/{addon.name}/{addon.version}/mcp"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return RedirectResponse(url, status_code=307)

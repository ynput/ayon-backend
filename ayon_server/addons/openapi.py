from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import HTMLResponse

from ayon_server.api.context import get_request_context
from ayon_server.config import ayonconfig
from ayon_server.exceptions import ForbiddenException

if TYPE_CHECKING:
    from .addon import BaseServerAddon


def _get_temp_app(addon: "BaseServerAddon") -> FastAPI:
    if ayonconfig.disable_rest_docs:
        raise ForbiddenException("OpenAPI documentation is disabled")

    if ayonconfig.openapi_require_authentication:
        ctx = get_request_context()
        user = ctx.user

        if user is None:
            raise ForbiddenException(
                "You must be logged in to access addon OpenAPI schema"
            )

        if not user.is_manager:
            raise ForbiddenException(
                "You are not allowed to access addon OpenAPI schema"
            )

    prefix = f"/api/addons/{addon.name}/{addon.version}"
    temp_app = FastAPI(
        title=addon.definition.friendly_name,
        version=addon.version,
    )
    for endpoint in addon.endpoints:
        path = endpoint["path"].lstrip("/")
        path = f"{prefix}/{path}"
        temp_app.add_api_route(
            path,
            endpoint["handler"],
            methods=[endpoint["method"]],
            name=endpoint["name"],
            description=endpoint["description"],
            operation_id=endpoint["name"],
        )

    def generate_unique_id(route):
        return route.name

    for router in addon.routers:
        temp_app.include_router(
            router,
            prefix=prefix,
            generate_unique_id_function=generate_unique_id,
        )

    return temp_app


def get_addon_openapi(addon: "BaseServerAddon") -> dict[str, str]:
    """Get OpenAPI schema for the addon"""
    temp_app = _get_temp_app(addon)
    router_openapi = temp_app.openapi()
    return router_openapi


def get_addon_api_docs(addon: "BaseServerAddon") -> HTMLResponse:
    """Get API docs for the addon"""

    openapi_url = f"/api/addons/{addon.name}/{addon.version}/openapi.json"
    title = addon.friendly_name

    return get_redoc_html(
        openapi_url=openapi_url,
        title=title,
        redoc_js_url="/docs/redoc.standalone.js",
    )

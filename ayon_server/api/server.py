import importlib
import os
import pathlib
import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocket, WebSocketDisconnect

# okay. now the rest
from ayon_server.api.auth import AuthMiddleware
from ayon_server.api.dependencies import CurrentUserOptional
from ayon_server.api.lifespan import lifespan
from ayon_server.api.logging import LoggingMiddleware
from ayon_server.api.messaging import messaging
from ayon_server.api.metadata import app_meta
from ayon_server.background.log_collector import log_collector
from ayon_server.config import ayonconfig
from ayon_server.exceptions import ForbiddenException
from ayon_server.graphql import router as graphql_router
from ayon_server.logging import log_traceback, logger

#
# We just need the log collector to be initialized.
#

_ = log_collector

#
# Let's create the app
#

app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    **app_meta,
)

app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)


#
# Documentation and OpenAPI endpoints
#


@app.get("/openapi.json", include_in_schema=False)
async def openapi(user: CurrentUserOptional) -> dict[str, Any]:
    """Return OpenAPI schema"""

    if ayonconfig.disable_rest_docs:
        raise ForbiddenException("OpenAPI documentation is disabled")

    if ayonconfig.openapi_require_authentication:
        if user is None:
            raise ForbiddenException("You must be logged in to access OpenAPI schema")

        if not user.is_manager:
            raise ForbiddenException("You are not allowed to access OpenAPI schema")

    return get_openapi(
        title=app_meta["title"],
        version=app_meta["version"],
        routes=app.routes,
        description=app_meta["description"],
    )


@app.get("/docs", include_in_schema=False)
async def docs(user: CurrentUserOptional) -> HTMLResponse:
    """Return the OpenAPI documentation page"""

    if ayonconfig.disable_rest_docs:
        raise ForbiddenException("OpenAPI documentation is disabled")

    if ayonconfig.openapi_require_authentication:
        if user is None:
            raise ForbiddenException(
                "You must be logged in to access API documentation"
            )

        if not user.is_manager:
            raise ForbiddenException("You are not allowed to access API documentation")

    return get_redoc_html(
        openapi_url="/openapi.json",
        title=app_meta["title"],
    )


#
# Handle request errors (not covered by the logging middleware)
#


@app.exception_handler(404)
def not_found_handler(request: Request, _):
    """Handle 404 errors"""
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=404,
            content={
                "code": 404,
                "detail": f"API endpoint {request.url.path} not found",
                "path": request.url.path,
            },
        )

    elif request.url.path.startswith("/addons"):
        return JSONResponse(
            status_code=404,
            content={
                "code": 404,
                "detail": f"Addon endpoint {request.url.path} not found",
                "path": request.url.path,
            },
        )

    return JSONResponse(
        status_code=404,
        content={
            "code": 404,
            "detail": f"File {request.url.path} not found",
            "path": request.url.path,
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    extras = {}
    if request.state.user:
        extras["user"] = request.state.user.name

    # use traceback field to pass the details
    # event tho it is not a traceback - but it
    # will be formatted nicely in the log

    traceback_msg = ""
    for error in exc.errors():
        loc = error["loc"]
        if len(loc) > 1:
            loc = loc[1:]
        loc = ".".join(str(x) for x in loc)
        traceback_msg += f"{loc}: {error['msg']}\n"

    detail = (
        f"Request validation error in " f"[{request.method.upper()}] {request.url.path}"
    )

    extras["traceback"] = traceback_msg.strip()
    logger.error(detail, **extras)
    return JSONResponse(
        status_code=400,
        content={
            "code": 400,
            "detail": detail,
            "path": request.url.path,
            "traceback": traceback_msg.strip(),
            "errors": exc.errors(),
        },
    )


#
# GraphQL
#

app.include_router(
    graphql_router,
    prefix="/graphql",
    tags=["GraphQL"],
    include_in_schema=False,
)


@app.get("/graphiql", include_in_schema=False)
def explorer() -> HTMLResponse:
    page = pathlib.Path("static/graphiql.html").read_text()
    page = page.replace("{{ SUBSCRIPTION_ENABLED }}", "false")  # TODO
    return HTMLResponse(page, 200)


#
# Websocket
#


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    client = await messaging.join(websocket)
    if client is None:
        return
    try:
        while True:
            message = await client.receive()
            if message is None:
                continue

            if (
                message["topic"] == "auth"
                and (token := message.get("token")) is not None
            ):
                await client.authorize(
                    token,
                    topics=message.get("subscribe", []),
                    project=message.get("project"),
                )
    except (RuntimeError, WebSocketDisconnect):
        try:
            del messaging.clients[client.id]
        except KeyError:
            pass


#
# REST endpoints
#


def init_api(target_app: FastAPI, plugin_dir: str = "api") -> None:
    """Register API modules to the server"""

    sys.path.insert(0, plugin_dir)
    for module_name in sorted(os.listdir(plugin_dir)):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            log_traceback(f"Unable to initialize {module_name}")
            continue

        if not hasattr(module, "router"):
            logger.debug(f"API plug-in '{module_name}' has no router")
            continue

        target_app.include_router(module.router, prefix="/api")

    # Use endpoints function names as operation_ids
    for route in app.routes:
        if isinstance(route, APIRoute):
            if route.operation_id is None:
                route.operation_id = route.name


def init_global_static(target_app: FastAPI) -> None:
    STATIC_DIR = "/storage/static"
    try:
        os.makedirs(STATIC_DIR, exist_ok=True)
    except Exception as e:
        logger.warning(f"Unable to create {STATIC_DIR}: {e}")
        return
    target_app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# API must be initialized here
# Because addons, which are initialized later
# may need access to classes initialized from the API (such as Attributes)

init_global_static(app)
init_api(app, ayonconfig.api_modules_dir)

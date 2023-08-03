import asyncio
import importlib
import inspect
import os
import pathlib
import sys
import traceback

import fastapi
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocket, WebSocketDisconnect

# from fastapi.middleware.cors import CORSMiddleware
from nxtools import log_traceback, logging

from ayon_server.access.roles import Roles
from ayon_server.addons import AddonLibrary
from ayon_server.api.messaging import Messaging
from ayon_server.api.metadata import app_meta, tags_meta
from ayon_server.api.responses import ErrorResponse
from ayon_server.auth.session import Session
from ayon_server.config import ayonconfig
from ayon_server.events import dispatch_event, update_event
from ayon_server.exceptions import AyonException, UnauthorizedException
from ayon_server.graphql import router as graphql_router
from ayon_server.helpers.thumbnail_cleaner import thumbnail_cleaner
from ayon_server.installer import background_installer
from ayon_server.lib.postgres import Postgres

# This needs to be imported first!
from ayon_server.logs import log_collector
from ayon_server.utils import parse_access_token

app = fastapi.FastAPI(
    docs_url=None,
    redoc_url="/docs",
    openapi_tags=tags_meta,
    **app_meta,
)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

#
# Static files
#


class AuthStaticFiles(StaticFiles):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    async def __call__(self, scope, receive, send) -> None:
        request = fastapi.Request(scope, receive)
        # TODO: use dep_current_user here in order to keep the behaviour consistent
        access_token = parse_access_token(request.headers.get("Authorization"))
        if access_token is None:
            access_token = request.headers.get("x-api-key")

        if access_token:
            try:
                session_data = await Session.check(access_token, None)
            except AyonException:
                pass
            else:
                if session_data:
                    await super().__call__(scope, receive, send)
                    return
        err_msg = "You need to be logged in in order to download this file"
        raise UnauthorizedException(err_msg)


#
# Error handling
#

logging.user = "server"


async def user_name_from_request(request: fastapi.Request) -> str:
    """Get user from request"""

    access_token = parse_access_token(request.headers.get("Authorization"))
    if not access_token:
        return "anonymous"
    try:
        session_data = await Session.check(access_token, None)
    except AyonException:
        return "anonymous"
    if not session_data:
        return "anonymous"
    user_name = session_data.user.name
    assert type(user_name) is str
    return user_name


@app.exception_handler(404)
async def custom_404_handler(request: fastapi.Request, _):
    """Redirect 404s to frontend."""

    if request.url.path.startswith("/api"):
        logging.error(f"404 {request.method} {request.url.path}")
        return fastapi.responses.JSONResponse(
            status_code=404,
            content={
                "code": 404,
                "detail": f"API endpoint {request.url.path} not found",
                "path": request.url.path,
            },
        )

    elif request.url.path.startswith("/addons"):
        logging.error(f"404 {request.method} {request.url.path}")
        return fastapi.responses.JSONResponse(
            status_code=404,
            content={
                "code": 404,
                "detail": f"Addon endpoint {request.url.path} not found",
                "path": request.url.path,
            },
        )

    index_path = os.path.join(ayonconfig.frontend_dir, "index.html")
    if os.path.exists(index_path):
        return fastapi.responses.FileResponse(
            index_path, status_code=200, media_type="text/html"
        )

    logging.error(f"404 {request.method} {request.url.path}")
    return fastapi.responses.JSONResponse(
        status_code=404,
        content={
            "code": 404,
            "detail": f"File {request.url.path} not found",
            "path": request.url.path,
        },
    )


@app.exception_handler(AyonException)
async def ayon_exception_handler(
    request: fastapi.Request,
    exc: AyonException,
) -> fastapi.responses.JSONResponse:
    user_name = await user_name_from_request(request)

    path = f"[{request.method.upper()}]"
    path += f" {request.url.path.removeprefix('/api')}"

    logging.error(f"{path}: {exc}", user=user_name)

    return fastapi.responses.JSONResponse(
        status_code=exc.status,
        content={
            "code": exc.status,
            "detail": exc.detail,
            "path": request.url.path,
            **exc.extra,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc) -> fastapi.responses.JSONResponse:
    logging.error(f"Validation error\n{exc}")
    detail = "Validation error"  # TODO: Be descriptive, but not too much
    return fastapi.responses.JSONResponse(
        status_code=400,
        content=ErrorResponse(code=400, detail=detail).dict(),
    )


@app.exception_handler(AssertionError)
async def assertion_exception_handler(request: fastapi.Request, exc: AssertionError):
    user_name = await user_name_from_request(request)
    path = f"[{request.method.upper()}]"
    path += f" {request.url.path.removeprefix('/api')}"

    tb = traceback.extract_tb(exc.__traceback__)
    fname, line_no, func, _ = tb[-1]

    detail = str(exc)
    payload = {
        "code": 500,
        "path": path,
        "file": fname,
        "function": func,
        "line": line_no,
    }

    logging.error(detail, user=user_name, **payload)
    return fastapi.responses.JSONResponse(status_code=500, content=payload)


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: fastapi.Request,
    exc: Exception,
) -> fastapi.responses.JSONResponse:
    user_name = await user_name_from_request(request)
    path = f"[{request.method.upper()}]"
    path += f" {request.url.path.removeprefix('/api')}"

    tb = traceback.extract_tb(exc.__traceback__)
    fname, line_no, func, _ = tb[-1]

    logging.error(f"{path}: UNHANDLED EXCEPTION", user=user_name)
    logging.error(exc)
    return fastapi.responses.JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "detail": "Internal server error",
            "traceback": f"{exc}",
            "path": path,
            "file": fname,
            "function": func,
            "line": line_no,
        },
    )


#
# GraphQL
#

app.include_router(
    graphql_router, prefix="/graphql", tags=["GraphQL"], include_in_schema=False
)


@app.get("/graphiql", include_in_schema=False)
def explorer() -> fastapi.responses.HTMLResponse:
    page = pathlib.Path("static/graphiql.html").read_text()
    page = page.replace("{{ SUBSCRIPTION_ENABLED }}", "false")  # TODO
    return fastapi.responses.HTMLResponse(page, 200)


#
# Websocket
#

messaging = Messaging()


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

            if message["topic"] == "auth":
                await client.authorize(
                    message.get("token"),
                    topics=message.get("subscribe", []),
                    project=message.get("project"),
                )
    except WebSocketDisconnect:
        # NOTE: Too noisy
        # if client.user_name:
        #     logging.info(f"{client.user_name} disconnected")
        # else:
        #     logging.info("Anonymous client disconnected")
        try:
            del messaging.clients[client.id]
        except KeyError:
            pass


#
# REST endpoints
#


def init_api(target_app: fastapi.FastAPI, plugin_dir: str = "api") -> None:
    """Register API modules to the server"""

    sys.path.insert(0, plugin_dir)
    for module_name in sorted(os.listdir(plugin_dir)):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            log_traceback(f"Unable to initialize {module_name}")
            continue

        if not hasattr(module, "router"):
            logging.error(f"API plug-in '{module_name}' has no router")
            continue

        target_app.include_router(module.router, prefix="/api")

    # Use endpoints function names as operation_ids
    for route in app.routes:
        if isinstance(route, fastapi.routing.APIRoute):
            if route.operation_id is None:
                route.operation_id = route.name


def init_addons(target_app: fastapi.FastAPI) -> None:
    """Serve static files for addon frontends."""
    for addon_name, addon_definition in AddonLibrary.items():
        for version in addon_definition.versions:
            addon = addon_definition.versions[version]
            if (fedir := addon.get_frontend_dir()) is not None:
                logging.debug(f"Initializing frontend dir {addon_name}:{version}")
                target_app.mount(
                    f"/addons/{addon_name}/{version}/frontend/",
                    StaticFiles(directory=fedir, html=True),
                )
            if (resdir := addon.get_public_dir()) is not None:
                logging.debug(f"Initializing public dir for {addon_name}:{version}")
                target_app.mount(
                    f"/addons/{addon_name}/{version}/public/",
                    StaticFiles(directory=resdir),
                )
            if (resdir := addon.get_private_dir()) is not None:
                logging.debug(f"Initializing private dir for {addon_name}:{version}")
                target_app.mount(
                    f"/addons/{addon_name}/{version}/private/",
                    AuthStaticFiles(directory=resdir),
                )


def init_frontend(target_app: fastapi.FastAPI, frontend_dir: str) -> None:
    """Initialize frontend endpoints."""
    if not os.path.isdir(frontend_dir):
        return
    target_app.mount("/", StaticFiles(directory=frontend_dir, html=True))


if os.path.isdir("/storage/static"):  # TODO: Make this configurable
    app.mount("/static", StaticFiles(directory="/storage/static"), name="static")


init_api(app, ayonconfig.api_modules_dir)
init_addons(app)
init_frontend(app, ayonconfig.frontend_dir)


#
# Start up
#


@app.on_event("startup")
async def startup_event() -> None:
    """Startup event.

    This is called after the server is started and:
        - initializes the log
        - initializes redis2websocket bridge
        - connects to the database
        - loads roles
    """

    # Save the process PID
    with open("/var/run/ayon.pid", "w") as f:
        f.write(str(os.getpid()))

    retry_interval = 5

    while True:
        try:
            await Postgres.connect()
        except Exception as e:
            msg = " ".join([str(k) for k in e.args])
            logging.error(f"Unable to connect to the database ({msg})", handlers=None)
            logging.info(f"Retrying in {retry_interval} seconds", handlers=None)
            await asyncio.sleep(retry_interval)
        else:
            break

    await Roles.load()
    log_collector.start()
    messaging.start()
    thumbnail_cleaner.start()
    background_installer.start()

    logging.info("Setting up addons")
    start_event = await dispatch_event("server.started", finished=False)

    library = AddonLibrary.getinstance()
    addon_records = list(AddonLibrary.items())
    if library.restart_requested:
        logging.warning("Restart requested, skipping addon setup")
        await dispatch_event(
            "server.restart_requested",
            description="Server restart requested during addon initialization",
        )
        return

    restart_requested = False
    for addon_name, addon in addon_records:
        for version in addon.versions.values():
            if inspect.iscoroutinefunction(version.setup):
                # Since setup may, but does not have to be async, we need to
                # silence mypy here.
                await version.setup()  # type: ignore
            else:
                version.setup()
            if (not restart_requested) and version.restart_requested:
                logging.warning(f"Restart requested during addon {addon_name} setup.")
                restart_requested = True

    if restart_requested:
        await dispatch_event(
            "server.restart_requested",
            description="Server restart requested during addon setup",
        )

    if start_event is not None:
        await update_event(
            start_event,
            status="finished",
            description="Server started",
        )
    logging.goodnews("Server is now ready to connect")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Shutdown event."""
    logging.info("Server is shutting down")

    await background_installer.shutdown()
    await log_collector.shutdown()
    await thumbnail_cleaner.shutdown()
    await messaging.shutdown()
    await Postgres.shutdown()
    logging.info("Server stopped", handlers=None)

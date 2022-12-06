import asyncio
import importlib
import inspect
import os
import pathlib
import sys

import fastapi
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocket, WebSocketDisconnect
from nxtools import log_traceback, logging

from openpype.access.roles import Roles
from openpype.addons import AddonLibrary
from openpype.api.messaging import Messaging
from openpype.api.metadata import app_meta, tags_meta
from openpype.api.responses import ErrorResponse
from openpype.auth.session import Session
from openpype.config import pypeconfig
from openpype.events import dispatch_event, update_event
from openpype.exceptions import OpenPypeException, UnauthorizedException
from openpype.graphql import router as graphql_router
from openpype.lib.postgres import Postgres

# This needs to be imported first!
from openpype.logs import log_collector
from openpype.utils import parse_access_token

app = fastapi.FastAPI(
    docs_url=None,
    redoc_url="/docs",
    openapi_tags=tags_meta,
    **app_meta,
)

#
# Static files
#


class AuthStaticFiles(StaticFiles):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    async def __call__(self, scope, receive, send) -> None:
        request = fastapi.Request(scope, receive)
        access_token = parse_access_token(request.headers.get("Authorization"))
        if access_token:
            try:
                session_data = await Session.check(access_token, None)
            except OpenPypeException:
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


@app.exception_handler(404)
async def custom_404_handler(_, __):
    """Redirect 404s to frontend."""
    return fastapi.responses.RedirectResponse("/")


async def user_name_from_request(request: fastapi.Request) -> str:
    """Get user from request"""

    access_token = parse_access_token(request.headers.get("Authorization"))
    if not access_token:
        return "anonymous"
    try:
        session_data = await Session.check(access_token, None)
    except OpenPypeException:
        return "anonymous"
    if not session_data:
        return "anonymous"
    user_name = session_data.user.name
    assert type(user_name) is str
    return user_name


@app.exception_handler(OpenPypeException)
async def openpype_exception_handler(
    request: fastapi.Request,
    exc: OpenPypeException,
) -> fastapi.responses.JSONResponse:
    user_name = await user_name_from_request(request)

    path = f"[{request.method.upper()}]"
    path += f" {request.url.path.removeprefix('/api')}"

    logging.error(f"{path}: {exc}", user=user_name)

    return fastapi.responses.JSONResponse(
        status_code=exc.status,
        content=ErrorResponse(code=exc.status, detail=exc.detail).dict(),
    )


@app.exception_handler(AssertionError)
async def assertion_error_handler(
    request: fastapi.Request,
    exc: AssertionError,
) -> fastapi.responses.JSONResponse:
    user_name = await user_name_from_request(request)

    path = f"[{request.method.upper()}]"
    path += f" {request.url.path.removeprefix('/api')}"
    message = exc.args[0] if exc.args else "Assertion failed"
    logging.error(f"{path}: {message}", user=user_name)
    return fastapi.responses.JSONResponse(
        status_code=500,
        content=ErrorResponse(code=500, detail=message).dict(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc) -> fastapi.responses.JSONResponse:
    logging.error(f"Validation error\n{exc}")
    detail = "Validation error"  # TODO: Be descriptive, but not too much
    return fastapi.responses.JSONResponse(
        status_code=400,
        content=ErrorResponse(code=400, detail=detail).dict(),
    )


@app.exception_handler(Exception)
async def all_exception_handler(
    request: fastapi.Request,
    exc: Exception,
) -> fastapi.responses.JSONResponse:
    user_name = await user_name_from_request(request)
    path = f"[{request.method.upper()}]"
    path += f" {request.url.path.removeprefix('/api')}"
    logging.error(f"{path}: UNHANDLED EXCEPTION", user=user_name)
    logging.error(exc)
    return fastapi.responses.JSONResponse(
        status_code=500,
        content=ErrorResponse(code=500, detail="Internal server error").dict(),
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
                )
    except WebSocketDisconnect:
        # NOTE: Too noisy
        # if client.user_name:
        #     logging.info(f"{client.user_name} disconnected")
        # else:
        #     logging.info("Anonymous client disconnected")
        del messaging.clients[client.id]


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
            route.operation_id = route.name


def init_frontend(target_app: fastapi.FastAPI, frontend_dir: str) -> None:
    """Initialize frontend endpoints."""
    if not os.path.isdir(frontend_dir):
        return
    target_app.mount(
        "/",
        StaticFiles(frontend_dir, html=True),
        name="frontend",
    )


def init_addons(target_app: fastapi.FastAPI) -> None:
    """Serve static files for addon frontends."""
    for addon_name, addon_definition in AddonLibrary.items():
        for version in addon_definition.versions:
            addon = addon_definition.versions[version]
            if (fedir := addon.get_frontend_dir()) is not None:
                logging.debug(f"Initializing frontend dir for {addon_name} {version}")
                target_app.mount(
                    f"/addons/{addon_name}/{version}/frontend",
                    StaticFiles(directory=fedir, html=True),
                )
            if (resdir := addon.get_public_dir()) is not None:
                logging.debug(f"Initializing public dir for {addon_name} {version}")
                target_app.mount(
                    f"/addons/{addon_name}/{version}/public",
                    StaticFiles(directory=resdir),
                )
            if (resdir := addon.get_private_dir()) is not None:
                logging.debug(f"Initializing private dir for {addon_name} {version}")
                target_app.mount(
                    f"/addons/{addon_name}/{version}/private",
                    AuthStaticFiles(directory=resdir),
                )


init_api(app, pypeconfig.api_modules_dir)
init_frontend(app, pypeconfig.frontend_dir)
init_addons(app)


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

    await log_collector.shutdown()
    await messaging.shutdown()
    await Postgres.shutdown()

    # tasks = []
    # for task in asyncio.all_tasks():
    #     task.cancel()
    #     tasks.append(task)
    #
    # while not all(task.done() for task in tasks):
    #     await asyncio.sleep(0.1)
    #     print("Waiting for tasks to finish")

    logging.info("Server stopped", handlers=None)

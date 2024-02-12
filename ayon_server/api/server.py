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
from nxtools import log_to_file, log_traceback, logging, slugify

from ayon_server.access.access_groups import AccessGroups
from ayon_server.addons import AddonLibrary
from ayon_server.api.messaging import Messaging
from ayon_server.api.metadata import app_meta, tags_meta
from ayon_server.api.postgres_exceptions import (
    IntegrityConstraintViolationError,
    parse_posgres_exception,
)
from ayon_server.api.responses import ErrorResponse
from ayon_server.auth.session import Session
from ayon_server.background.workers import background_workers
from ayon_server.config import ayonconfig
from ayon_server.events import dispatch_event, update_event
from ayon_server.exceptions import AyonException, UnauthorizedException
from ayon_server.graphql import router as graphql_router
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import parse_access_token

app = fastapi.FastAPI(
    docs_url=None,
    redoc_url="/docs" if not ayonconfig.disable_rest_docs else None,
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

logging.user = f"server_{os.getpid()}"
if ayonconfig.log_file:
    logging.add_handler(log_to_file(ayonconfig.log_file))


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
    assert isinstance(user_name, str)
    return user_name


@app.exception_handler(404)
async def custom_404_handler(request: fastapi.Request, _):
    """Redirect 404s to frontend."""

    if request.url.path.startswith("/api"):
        return fastapi.responses.JSONResponse(
            status_code=404,
            content={
                "code": 404,
                "detail": f"API endpoint {request.url.path} not found",
                "path": request.url.path,
            },
        )

    elif request.url.path.startswith("/addons"):
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
    if exc.status in [401, 403, 503]:
        # do not store 401 and 403 errors in the logs
        return fastapi.responses.JSONResponse(
            status_code=exc.status,
            content={
                "code": exc.status,
                "detail": exc.detail,
            },
        )

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
async def validation_exception_handler(
    request: fastapi.Request,
    exc: RequestValidationError,
) -> fastapi.responses.JSONResponse:
    logging.error(f"Validation error\n{exc}")
    detail = "Validation error"  # TODO: Be descriptive, but not too much
    return fastapi.responses.JSONResponse(
        status_code=400,
        content=ErrorResponse(code=400, detail=detail).dict(),
    )


@app.exception_handler(IntegrityConstraintViolationError)
async def integrity_constraint_violation_error_handler(
    request: fastapi.Request,
    exc: IntegrityConstraintViolationError,
) -> fastapi.responses.JSONResponse:
    path = f"[{request.method.upper()}]"
    path += f" {request.url.path.removeprefix('/api')}"

    tb = traceback.extract_tb(exc.__traceback__)
    fname, line_no, func, _ = tb[-1]

    payload = {
        "path": path,
        "file": fname,
        "function": func,
        "line": line_no,
        **parse_posgres_exception(exc),
    }

    return fastapi.responses.JSONResponse(status_code=payload["code"], content=payload)


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
    graphql_router,
    prefix="/graphql",
    tags=["GraphQL"],
    include_in_schema=False,
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


def init_addon_endpoints(target_app: fastapi.FastAPI) -> None:
    library = AddonLibrary.getinstance()
    for addon_name, addon_definition in library.items():
        for version in addon_definition.versions:
            addon = addon_definition.versions[version]

            if hasattr(addon, "ws"):
                target_app.add_api_websocket_route(
                    f"/api/addons/{addon_name}/{version}/ws",
                    addon.ws,
                    name=f"{addon_name}_{version}_ws",
                )

            for endpoint in addon.endpoints:
                path = endpoint["path"].lstrip("/")
                first_element = path.split("/")[0]
                # TODO: site settings? other routes?
                if first_element in ["settings", "schema", "overrides"]:
                    logging.error(f"Unable to assing path to endpoint: {path}")
                    continue

                path = f"/api/addons/{addon_name}/{version}/{path}"
                target_app.add_api_route(
                    path,
                    endpoint["handler"],
                    methods=[endpoint["method"]],
                    name=endpoint["name"],
                    tags=[f"{addon_definition.friendly_name} {version}"],
                    operation_id=slugify(
                        f"{addon_name}_{version}_{endpoint['name']}",
                        separator="_",
                    ),
                )


def init_addon_static(target_app: fastapi.FastAPI) -> None:
    """Serve static files for addon frontends."""
    for addon_name, addon_definition in AddonLibrary.items():
        for version in addon_definition.versions:
            addon = addon_definition.versions[version]
            static_dirs = []
            if (fedir := addon.get_frontend_dir()) is not None:
                static_dirs.append("frontend")
                target_app.mount(
                    f"/addons/{addon_name}/{version}/frontend/",
                    StaticFiles(directory=fedir, html=True),
                )
            if (resdir := addon.get_public_dir()) is not None:
                static_dirs.append("public")
                target_app.mount(
                    f"/addons/{addon_name}/{version}/public/",
                    StaticFiles(directory=resdir),
                )
            if (resdir := addon.get_private_dir()) is not None:
                static_dirs.append("private")
                target_app.mount(
                    f"/addons/{addon_name}/{version}/private/",
                    AuthStaticFiles(directory=resdir),
                )

            if static_dirs:
                logging.debug(
                    f"Initialized static dirs for {addon_name}:{version}: {', '.join(static_dirs)}"
                )


def init_frontend(target_app: fastapi.FastAPI, frontend_dir: str) -> None:
    """Initialize frontend endpoints."""
    if not os.path.isdir(frontend_dir):
        return
    target_app.mount("/", StaticFiles(directory=frontend_dir, html=True))


if os.path.isdir("/storage/static"):  # TODO: Make this configurable
    app.mount("/static", StaticFiles(directory="/storage/static"), name="static")

# API must be initialized here
# Because addons, which are initialized later
# may need access to classes initialized from the API (such as Attributes)
init_api(app, ayonconfig.api_modules_dir)

#
# Start up
#


@app.on_event("startup")
async def startup_event() -> None:
    """Startup event.

    This is called after the server is started and:
        - initializes background workers
        - initializes redis2websocket bridge
        - connects to the database
        - loads access groups
    """

    # Save the process PID
    with open("/var/run/ayon.pid", "w") as f:
        f.write(str(os.getpid()))

    retry_interval = 5

    # Connect to the database

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

    await AccessGroups.load()

    # Start background tasks

    background_workers.start()

    messaging.start()

    # Initialize addons

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
    bad_addons = {}
    for addon_name, addon in addon_records:
        for version in addon.versions.values():
            try:
                if inspect.iscoroutinefunction(version.pre_setup):
                    # Since setup may, but does not have to be async, we need to
                    # silence mypy here.
                    await version.pre_setup()  # type: ignore
                else:
                    version.pre_setup()
                if (not restart_requested) and version.restart_requested:
                    logging.warning(
                        f"Restart requested during addon {addon_name} pre-setup."
                    )
                    restart_requested = True
            except Exception as e:
                log_traceback(f"Error during {addon_name} {version.version} pre-setup")
                reason = {
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
                bad_addons[(addon_name, version.version)] = reason

    for addon_name, addon in addon_records:
        for version in addon.versions.values():
            try:
                if inspect.iscoroutinefunction(version.setup):
                    await version.setup()
                else:
                    version.setup()
                if (not restart_requested) and version.restart_requested:
                    logging.warning(
                        f"Restart requested during addon {addon_name} setup."
                    )
                    restart_requested = True
            except Exception as e:
                log_traceback(f"Error during {addon_name} {version.version} setup")
                reason = {
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
                bad_addons[(addon_name, version.version)] = reason

    for _addon_name, _addon_version in bad_addons:
        logging.error(
            f"Addon {_addon_name} {_addon_version} failed to initialize. Unloading."
        )
        reason = bad_addons[(_addon_name, _addon_version)]
        library.unload_addon(_addon_name, _addon_version, reason=reason)

    if restart_requested:
        await dispatch_event(
            "server.restart_requested",
            description="Server restart requested during addon setup",
        )
    else:
        # Initialize endpoints for active addons
        init_addon_endpoints(app)

        # Addon static dirs must stay exactly here
        init_addon_static(app)

        # Frontend must be initialized last (since it is mounted to /)
        init_frontend(app, ayonconfig.frontend_dir)

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

    await background_workers.shutdown()
    await messaging.shutdown()
    await Postgres.shutdown()
    logging.info("Server stopped", handlers=None)

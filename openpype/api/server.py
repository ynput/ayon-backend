import asyncio
import importlib
import os
import sys

import fastapi
from fastapi.websockets import WebSocket, WebSocketDisconnect
from nxtools import log_traceback, logging

from openpype.access.roles import Roles
from openpype.api.messaging import Messaging
from openpype.api.metadata import app_meta, tags_meta
from openpype.api.responses import ErrorResponse
from openpype.auth.session import Session
from openpype.config import pypeconfig
from openpype.exceptions import OpenPypeException
from openpype.graphql import router as graphql_router
from openpype.lib.postgres import Postgres
from openpype.utils import parse_access_token

app = fastapi.FastAPI(
    docs_url=None,
    redoc_url="/docs",
    openapi_tags=tags_meta,
    **app_meta,
)

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
    except OpenPypeException:
        return "anonymous"
    if not session_data:
        return "anonymous"
    return session_data.user.name


@app.exception_handler(OpenPypeException)
async def openpype_exception_handler(request: fastapi.Request, exc: OpenPypeException):
    user_name = await user_name_from_request(request)

    path = f"[{request.method.upper()}]"
    path += f" {request.url.path.removeprefix('/api')}"

    logging.error(f"{path}: {exc}", user=user_name)

    return fastapi.responses.JSONResponse(
        status_code=exc.status,
        content=ErrorResponse(code=exc.status, detail=exc.detail).dict(),
    )


@app.exception_handler(Exception)
async def all_exception_handler(request: fastapi.Request, exc: Exception):
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
def explorer():
    # TODO: use async load here
    with open("static/graphiql.html") as f:
        page = f.read()
    page = page.replace("{{ SUBSCRIPTION_ENABLED }}", "false")
    return fastapi.responses.HTMLResponse(page, 200)


#
# Websocket
#

messaging = Messaging()


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await messaging.join(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Message text was: {data}")
    except WebSocketDisconnect:
        await messaging.leave(websocket)


#
# REST endpoints
#


def init_api(target_app: fastapi.FastAPI, plugin_dir: str = "api"):
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


init_api(app, pypeconfig.api_modules_dir)


#
# Start up
#


@app.on_event("startup")
async def startup_event():
    """Startup event.

    This is called after the server is started and:
        - connects to the database
        - loads roles
    """
    retry_interval = 5
    while True:
        try:
            await Postgres.connect()
        except Exception as e:
            msg = " ".join([str(k) for k in e.args])
            logging.error(f"Unable to connect to the database ({msg})")
            logging.info(f"Retrying in {retry_interval} seconds")
            await asyncio.sleep(retry_interval)
        else:
            break

    await Roles.load()
    logging.goodnews("Server started")

import asyncio
import imp
import os

import fastapi
from nxtools import log_traceback, logging

from openpype.access.roles import Roles
from openpype.api.exceptions import APIException
from openpype.api.metadata import app_meta, tags_meta
from openpype.api.responses import ErrorResponse
from openpype.config import pypeconfig
from openpype.graphql import router as graphql_router
from openpype.lib.postgres import Postgres

app = fastapi.FastAPI(
    docs_url=None, redoc_url="/docs", openapi_tags=tags_meta, **app_meta
)

#
# Error handling
#


@app.exception_handler(APIException)
async def pype_exception_handler(request: fastapi.Request, exc: APIException):
    return fastapi.responses.JSONResponse(
        status_code=exc.status,
        content=ErrorResponse(code=exc.status, detail=exc.detail).dict(),
    )


@app.exception_handler(Exception)
async def all_exception_handler(request: fastapi.Request, exc: APIException):
    logging.error(f"Unhandled exception: {exc}")
    return fastapi.responses.JSONResponse(
        status_code=500,
        content=ErrorResponse(code=500, detail="Interanal server error").dict(),
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
# REST endpoints
#


def init_api(target_app: fastapi.FastAPI, plugin_dir: str = "api"):
    """Register API modules to the server"""

    for module_name in sorted(os.listdir(plugin_dir)):
        try:
            fp, pathname, description = imp.find_module(module_name, [plugin_dir])
        except ImportError:
            logging.error(f"API plug-in '{module_name}' is not a valid module")
            continue

        try:
            module = imp.load_module(module_name, fp, pathname, description)
        except Exception:
            log_traceback(f"Unable to load API plug-in '{module_name}'")
            continue

        # Ensure the module has a router
        if not hasattr(module, "router"):
            logging.error(f"API plug-in '{module_name}' has no router")
            continue

        # And include it in the app
        target_app.include_router(module.router, prefix="/api")


init_api(app, pypeconfig.api_modules_dir)


#
# Start up
#


@app.on_event("startup")
async def startup_event():
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

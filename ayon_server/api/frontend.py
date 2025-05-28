import os
from functools import cache

import fastapi
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from ayon_server.config import ayonconfig

NO_CACHE = {"remoteEntry.js"}


@cache
def get_index() -> fastapi.responses.HTMLResponse:
    # Index.html file is read from the server cache
    # to avoid reading it from the disk on every request
    # It is very small and shouldn't change during runtime
    # But we don't want to cache it in the browser,
    # because of the hashes of js and css files
    # - when they change, the browser should reload the index.html

    frontend_dir = ayonconfig.frontend_dir
    index_path = os.path.join(frontend_dir, "index.html")
    if not os.path.isfile(index_path):
        content = "frontend not found"
    with open(index_path) as file:
        content = file.read()
    return fastapi.responses.HTMLResponse(
        content, headers={"Cache-Control": "no-cache"}
    )


class FrontendFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> fastapi.responses.Response:
        # For the root path, return the index.html file
        # from the server cache (it shouldn't change during runtime)
        if path in [".", "", "/", "index.html"]:
            return get_index()

        if path in NO_CACHE:
            # for some files, we want to disable caching by explicitly
            # setting the Cache-Control header to no-cache
            response = await super().get_response(path, scope)
            response.headers["Cache-Control"] = "no-cache"
            return response

        try:
            # For other paths, return the file from the static files directory
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                # Propagate non-404 errors
                raise exc

            # Frontend is mounted to /, so we need to handle 404 errors
            # for the /api/ and /addons/ paths (in order to trigger the
            # correct 404 handler instead of falling back to the index.html)

            if path.startswith("api/"):
                # Propagate 404 errors for the /api/ path
                raise exc
            if path.startswith("addons/"):
                # Propagate 404 errors for the /addons/ path
                raise exc

            # For 404 errors, return the index.html file from the server cache
            # that handles the routing on the client side
            return get_index()


def init_frontend(target_app: fastapi.FastAPI) -> None:
    """Initialize frontend endpoints."""
    frontend_dir = os.path.abspath(ayonconfig.frontend_dir)
    if not os.path.isdir(frontend_dir):
        return
    target_app.mount("/", FrontendFiles(directory=frontend_dir, html=True))

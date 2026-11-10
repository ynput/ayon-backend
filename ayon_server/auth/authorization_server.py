"""Authorization server provided by an addon.

The server itself does not issue tokens to third-party applications. An
addon may: the production version of the addon named `oauth` that has an
`authorization_server` attribute implementing AuthorizationServer. The
server gives it what an addon cannot have on its own:

- `/api/oauth/...`: a path that does not change with the addon version
  (see api/oauth_server),
- `/.well-known/...`: the documents clients discover it by,
- the `WWW-Authenticate` header of 401 responses.

Without such an addon, nothing here answers and 401 responses are unchanged.
"""

import time
from typing import Protocol, runtime_checkable

from starlette.requests import Request
from starlette.responses import Response

from ayon_server.addons.library import AddonLibrary
from ayon_server.logging import log_traceback

AUTH_SERVER_ADDON = "oauth"

# The production bundle is read from the database. Unauthorized requests
# are frequent, so the answer is kept for a moment.
_VERSION_TTL = 10
_version: tuple[float, str | None] | None = None


@runtime_checkable
class AuthorizationServer(Protocol):
    async def handle_request(self, request: Request, path: str) -> Response:
        """Answer a request to /api/oauth/{path}."""
        ...

    async def handle_well_known(self, request: Request, path: str) -> Response | None:
        """Answer a request to /.well-known/{path}, or None for a 404."""
        ...

    async def get_challenge(self, request: Request) -> str | None:
        """Return the WWW-Authenticate value for a 401 to this request."""
        ...


async def _get_production_version() -> str | None:
    global _version
    now = time.monotonic()
    if _version is None or now - _version[0] > _VERSION_TTL:
        library = AddonLibrary.getinstance()
        active_versions = await library.get_active_versions()
        version = active_versions.get(AUTH_SERVER_ADDON, {}).get("production")
        _version = (now, version)
    return _version[1]


async def get_authorization_server() -> AuthorizationServer | None:
    library = AddonLibrary.getinstance()
    if AUTH_SERVER_ADDON not in library:
        return None  # not installed: nothing to look up
    version = await _get_production_version()
    if version is None:
        return None
    try:
        addon = library[AUTH_SERVER_ADDON][version]
    except KeyError:
        return None  # in the bundle, but failed to load
    server = getattr(addon, "authorization_server", None)
    if isinstance(server, AuthorizationServer):
        return server
    return None


async def get_bearer_challenge(request: Request) -> str | None:
    """Return the WWW-Authenticate value for a 401 response, if any.

    Never raises: a failing addon must not turn a 401 into a 500.
    """
    try:
        server = await get_authorization_server()
        if server is None:
            return None
        return await server.get_challenge(request)
    except Exception:
        log_traceback("Unable to get the authorization server challenge")
        return None

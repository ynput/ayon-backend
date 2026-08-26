from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# /livez must always report the process as alive, and /readyz needs to
# reach its own handler to report its own status - neither should be
# short-circuited by this middleware.
STARTUP_PROBE_PATHS = ("/livez", "/readyz")


class ReadinessMiddleware(BaseHTTPMiddleware):
    """Reject every request but the startup probes until the server is ready.

    Placed outermost in the middleware stack (added last in server.py, so
    it runs first) and ahead of AuthMiddleware specifically, so that
    nothing - including auth, which touches Postgres/Redis - runs before
    the database, Redis, and addons have finished initializing. Without
    this, a request made during startup could hit e.g. Postgres.acquire()'s
    assertion instead of a clean 503.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path not in STARTUP_PROBE_PATHS and not getattr(
            request.app.state, "ready", False
        ):
            return JSONResponse(
                status_code=503,
                content={"code": 503, "detail": "Server is starting up"},
            )

        return await call_next(request)

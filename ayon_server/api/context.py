import contextlib
from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from ayon_server.entities.user import UserEntity


@dataclass
class RequestContext:
    """
    Context of the request, which can be used to store additional information
    about the request, such as the user making the request, the project, etc.
    """

    user: UserEntity | None = None
    sender: str | None = None
    sender_type: str | None = None


request_context: ContextVar[RequestContext | None] = ContextVar(
    "request_context", default=None
)


def get_request_context() -> RequestContext:
    """
    Get the request context for the current request.

    Returns:
        RequestContext: The request context for the current request.
    """
    return request_context.get() or RequestContext()


@contextlib.asynccontextmanager
async def request_context_manager(context: RequestContext) -> AsyncIterator[None]:
    """
    Context manager for setting the request context for the current request.

    Args:
        context (RequestContext): The request context to set for the current request.
    """
    token = request_context.set(context)
    try:
        yield
    finally:
        request_context.reset(token)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware for setting the request context for each request.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            user = request.state.user
        except AttributeError:
            user = None

        context = RequestContext(
            user=user,
            sender=request.headers.get("X-Sender"),
            sender_type=request.headers.get("X-Sender-Type"),
        )
        async with request_context_manager(context):
            response = await call_next(request)
        return response

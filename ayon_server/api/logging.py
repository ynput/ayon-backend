import time
import traceback

from fastapi import Request, Response
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from shortuuid import ShortUUID
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect

from ayon_server.api.dependencies import NoTraces
from ayon_server.exceptions import AyonException
from ayon_server.lib.postgres_exceptions import (
    IntegrityConstraintViolationError,
    parse_postgres_exception,
)
from ayon_server.logging import log_exception, logger


def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "detail": exc.detail,
            "path": request.url.path,
        },
    )


def handle_ayon_exception(request: Request, exc: AyonException) -> JSONResponse:
    if exc.status in [401, 403, 503]:
        # unauthorized, forbidden, service unavailable
        # we don't need any additional details for these nor log them
        return JSONResponse(
            status_code=exc.status,
            content={
                "code": exc.status,
                "detail": exc.detail,
            },
        )

    if exc.status == 500:
        logger.error(f"{exc}")
    else:
        logger.debug(f"{exc}")

    return JSONResponse(
        status_code=exc.status,
        content={
            "code": exc.status,
            "detail": exc.detail,
            **exc.extra,
        },
    )


def handle_constraint_violation(
    request: Request,
    exc: IntegrityConstraintViolationError,
) -> JSONResponse:
    path = f"[{request.method.upper()}]"
    path += f" {request.url.path.removeprefix('/api')}"

    tb = traceback.extract_tb(exc.__traceback__)
    fname, line_no, func, _ = tb[-1]

    payload = {
        "path": path,
        "file": fname,
        "function": func,
        "line": line_no,
        **parse_postgres_exception(exc),
    }

    return JSONResponse(status_code=500, content=payload)


def handle_assertion_error(request: Request, exc: AssertionError) -> JSONResponse:
    path = f"[{request.method.upper()}]"
    path += f" {request.url.path.removeprefix('/api')}"

    tb = traceback.extract_tb(exc.__traceback__)
    fname, line_no, func, _ = tb[-1]

    detail = str(exc)

    extras = {
        "path": path,
        "file": fname,
        "function": func,
        "line": line_no,
    }
    if request.state.user:
        extras["user"] = request.state.user.name

    with logger.contextualize(**extras):
        logger.error(detail)

    extras["detail"] = detail
    extras["status"] = 500
    return JSONResponse(status_code=500, content=extras)


def handle_undhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    extras = {}
    if request.state.user:
        extras["user"] = request.state.user.name

    res = log_exception(exc, **extras)
    return JSONResponse(status_code=res["status"], content=res)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = ShortUUID().random(length=16)
        context = {"request_id": request_id}
        path = request.url.path

        with logger.contextualize(**context):
            start_time = time.perf_counter()
            try:
                response = await call_next(request)
            except AyonException as e:
                # Custom Ayon exceptions
                response = handle_ayon_exception(request, e)

            except ClientDisconnect:
                # Client disconnected
                response = Response(status_code=499)

            except HTTPException as e:
                # FastAPI / Starlette HTTP exceptions
                response = handle_http_exception(request, e)

            except IntegrityConstraintViolationError as e:
                # PostgreSQL constraint violation
                response = handle_constraint_violation(request, e)

            except AssertionError as e:
                # AssertionError
                response = handle_assertion_error(request, e)

            except Exception as e:
                # Unhandled exceptions
                response = handle_undhandled_exception(request, e)

            # except ExceptionGroup as eg:
            #     response = handle_exception_group(eg)

            # Before processing the request, we don't have access to
            # the route information, so we need to check it here
            # (that's also why we don't track the beginning of the request)
            should_trace = path.startswith("/api")  # or path.startswith("/graphql")

            if should_trace and (route := request.scope.get("route")):
                # We don't need to log successful requests to routes,
                # that have "NoTraces" dependencies.
                # They are usually heartbeats that pollute the logs.
                if isinstance(route, APIRoute):
                    for dependency in route.dependencies:
                        if dependency == NoTraces:
                            should_trace = False

            if should_trace:
                extras = {
                    "nodb": True,  # don't store in the event stream
                }
                if request.state.user:
                    extras["user"] = request.state.user.name

                process_time = round(time.perf_counter() - start_time, 3)
                f_result = f"| {response.status_code} in {process_time}s"
                with logger.contextualize(**extras):
                    logger.trace(f"[{request.method}] {path} {f_result}")

        return response

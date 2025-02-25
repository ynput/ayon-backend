import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ayon_server.auth.session import Session
from ayon_server.auth.utils import hash_password
from ayon_server.entities import UserEntity
from ayon_server.exceptions import UnauthorizedException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.utils import create_uuid
from ayon_server.utils.strings import parse_api_key


async def user_from_api_key(api_key: str) -> UserEntity:
    """Return a user associated with the given API key.

    Hashed ApiKey may be stored in the database in two ways:

    1. As a string in the `apiKey` field. Original method used
       by services

    2. As an array of objects in the `apiKeys` field. Each object
       has the following fields:
        - id: identifier that allows invalidating the key
        - key: hashed api key
        - label: a human-readable label
        - preview: a preview of the key
        - created: timestamp when the key was created
        - expires(optional): timestamp when the key expires

       In this case, the key is stored in the `key` field,
       is the one we are looking for. We also need to check
       if the key is not expired.
    """
    hashed_key = hash_password(api_key)
    query = """
        SELECT * FROM users
        WHERE data->>'apiKey' = $1
        OR EXISTS (
            SELECT 1 FROM jsonb_array_elements(data->'apiKeys') AS ak
            WHERE ak->>'key' = $1
        )
    """
    if not (result := await Postgres.fetch(query, hashed_key)):
        raise UnauthorizedException("Invalid API key")
    user = UserEntity.from_record(result[0])
    if user.data.get("apiKey") == hashed_key:
        return user
    for key_data in user.data.get("apiKeys", []):
        if key_data.get("key") != hashed_key:
            continue
        if key_data.get("expires") and key_data["expires"] < time.time():
            raise UnauthorizedException("API key has expired")
        return user
    raise UnauthorizedException("Invalid API key. This shouldn't happen")


async def user_from_request(request: Request) -> UserEntity:
    """Get user from request"""

    # Try loading API KEY
    # API Key may be stored as x-api-key header or as
    # authorization: apikey <key> header

    api_key = request.headers.get("x-api-key")
    if not api_key:
        authorization = request.headers.get("Authorization")
        if authorization:
            api_key = parse_api_key(authorization)

    if api_key:
        if (session_data := await Session.check(api_key, request)) is None:
            user = await user_from_api_key(api_key)
            session_data = await Session.create(user, request, token=api_key)
        session_data.is_api_key = True


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = create_uuid()
        context = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        }

        with logger.contextualize(**context):
            start_time = time.perf_counter()

            response = await call_next(request)  # Call next middleware/endpoint

            process_time = round(time.perf_counter() - start_time, 3)
            logger.trace("Request finished", process_time=process_time)

        return response

        # Extract token (example)
        # token = request.headers.get("Authorization")
        # user_id = None

        # if token:
        #     # Fake authentication process
        #     if token == "Bearer my-secret-token":
        #         user_id = "user_123"  # In real case, decode JWT or check DB
        #         request.state.user = user_id  # Attach user info to request
        #         logger.info(f"Authenticated user: {user_id}")
        #     else:
        #         logger.warning("Invalid authentication token")
        #         return Response("Unauthorized", status_code=401)

        # Log request metadata
        logger.info(f"Request: {request.method} {request.url}")

        # Log response time
        duration = time.time() - start_time
        logger.info(f"Response: {response.status_code} ({duration:.4f}s)")

        return response

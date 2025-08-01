import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ayon_server.auth.session import Session
from ayon_server.auth.utils import hash_password
from ayon_server.entities import UserEntity
from ayon_server.exceptions import UnauthorizedException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.utils.strings import parse_access_token, parse_api_key


def access_token_from_request(request: Request) -> str | None:
    token = request.cookies.get("accessToken")
    if not token:
        authorization = request.headers.get("Authorization")
        if authorization:
            token = parse_access_token(authorization)
    if not token:
        token = request.query_params.get("token")
    return token


async def get_logout_reason(token: str) -> str:
    reason = await Redis.get_json("logoutreason", token)
    if not reason:
        res = await Postgres.fetch(
            """
            SELECT description FROM public.events
            WHERE topic = 'auth.logout'
            AND summary->>'token' = $1
            AND created_at > NOW() - interval '5 minutes'
            ORDER BY created_at DESC LIMIT 1
            """,
            token,
        )
        if res:
            reason = res[0]["description"]
        else:
            reason = "Invalid session"
        await Redis.set_json("logoutreason", "token", reason, ttl=600)
    return reason


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
        SELECT * FROM public.users
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

    access_token: str | None = None

    if api_key:
        if (session_data := await Session.check(api_key, request)) is None:
            user = await user_from_api_key(api_key)
            session_data = await Session.create(user, request, token=api_key)
        session_data.is_api_key = True

    elif access_token := access_token_from_request(request):
        session_data = await Session.check(access_token, request)
    else:
        raise UnauthorizedException("Access token is missing")

    if not session_data:
        if access_token:
            reason = await get_logout_reason(access_token)
        else:
            reason = "Invalid API key"
        logger.trace(f"Unauthorized request: {reason}")
        raise UnauthorizedException(reason)

    await Redis.incr("user-requests", session_data.user.name)
    user = UserEntity.from_record(session_data.user.dict())
    user.add_session(session_data)

    if (x_as_user := request.headers.get("x-as-user")) and user.is_service:
        # sudo :)
        user = await UserEntity.load(x_as_user)

    return user


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        context = {}

        try:
            user = await user_from_request(request)
            context["user"] = user.name
            request.state.user = user
            request.state.unauthorized_reason = None
        except UnauthorizedException as e:
            request.state.user = None
            request.state.unauthorized_reason = str(e)

        with logger.contextualize(**context):
            response = await call_next(request)

        return response

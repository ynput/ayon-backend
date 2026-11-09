"""Login state bound to the browser of a user who is not logged in yet.

External login flows (OAuth / OIDC in the SSO addon and similar) need a
`state` parameter that only the browser which started the flow can complete.
The browser gets a random id in the HttpOnly `ayonPreAuth` cookie, and the
state is an encrypted token containing a hash of that id, so it is stateless
(nothing is written to Redis) and useless in any other browser.

Usage in an addon:

    state = await create_login_state("sso", {"provider": "google"})
    ...
    data = await verify_login_state(state, "sso")  # in the callback
"""

import hmac
import re
import secrets
import time
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from ayon_server.api.context import PreAuth, get_request_context
from ayon_server.exceptions import UnauthorizedException
from ayon_server.helpers.crypto import decrypt_json_urlsafe, encrypt_json_urlsafe
from ayon_server.utils import hash_data

COOKIE_NAME = "ayonPreAuth"
COOKIE_MAX_AGE = 24 * 3600
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")  # secrets.token_urlsafe(32)


def pre_auth_from_request(request: Request) -> PreAuth:
    """Read the id from the cookie, ignoring malformed values."""
    value = request.cookies.get(COOKIE_NAME)
    if value and _ID_PATTERN.match(value):
        return PreAuth(id=value)
    return PreAuth()


def apply_pre_auth_cookie(request: Request, response: Response) -> None:
    """Called by AuthMiddleware after the handler ran."""
    pre_auth: PreAuth | None = getattr(request.state, "pre_auth", None)
    if pre_auth is None:
        return

    if request.state.user is not None:
        # Logged in: the id has done its job, so a new login gets a new one
        if COOKIE_NAME in request.cookies:
            response.delete_cookie(COOKIE_NAME, path="/")
        return

    if pre_auth.created and pre_auth.id:
        scheme = request.headers.get("X-Forwarded-Proto", request.url.scheme)
        response.set_cookie(
            COOKIE_NAME,
            pre_auth.id,
            max_age=COOKIE_MAX_AGE,
            path="/",
            httponly=True,
            # Browsers drop Secure cookies on plain http (except localhost)
            secure=scheme.split(",")[0].strip() == "https",
            samesite="lax",
        )


def _get_pre_auth_id(create: bool) -> str | None:
    pre_auth = get_request_context().pre_auth
    if pre_auth is None:
        if create:
            raise RuntimeError("Login state requires an HTTP request context")
        return None
    if create:
        if pre_auth.id is None:
            pre_auth.id = secrets.token_urlsafe(32)
        # Re-send the cookie, so it cannot expire during the login
        pre_auth.created = True
    return pre_auth.id


async def create_login_state(purpose: str, data: dict[str, Any] | None = None) -> str:
    """Return an opaque, URL-safe state token bound to this browser.

    `purpose` separates flows (e.g. "sso"), so a state created for one
    cannot be used in another. `data` (JSON-serializable) is encrypted
    into the token and returned by `verify_login_state`.
    """
    pre_auth_id = _get_pre_auth_id(create=True)
    payload = {
        "data": data or {},
        "pid": hash_data(pre_auth_id),
        "purpose": purpose,
        # Unique state even for identical data within the same second
        "nonce": secrets.token_urlsafe(8),
    }
    encrypted = await encrypt_json_urlsafe(payload)
    return encrypted.token


async def verify_login_state(
    state: str | None,
    purpose: str,
    max_age: int = 600,
) -> dict[str, Any]:
    """Check the state against the cookie and return its data.

    Raises UnauthorizedException when the state is missing, forged,
    expired, created for another purpose or in another browser.
    """
    if not state:
        raise UnauthorizedException("Missing login state")

    pre_auth_id = _get_pre_auth_id(create=False)
    if not pre_auth_id:
        raise UnauthorizedException("Login session not found. Please try again.")

    try:
        decrypted = await decrypt_json_urlsafe(state)
    except Exception as e:
        raise UnauthorizedException("Invalid login state") from e

    payload = decrypted.data
    if payload.get("purpose") != purpose:
        raise UnauthorizedException("Invalid login state")
    if not hmac.compare_digest(str(payload.get("pid", "")), hash_data(pre_auth_id)):
        raise UnauthorizedException("Login was started in another browser")
    if time.time() - decrypted.timestamp > max_age:
        raise UnauthorizedException("Login expired. Please try again.")

    data: dict[str, Any] = payload.get("data", {})
    return data

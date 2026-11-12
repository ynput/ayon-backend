"""Login state is bound to the ayonPreAuth cookie, expires and is purpose-scoped."""

from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from ayon_server.api.context import PreAuth, RequestContext, request_context_manager
from ayon_server.auth import preauth
from ayon_server.exceptions import UnauthorizedException
from ayon_server.helpers import crypto

KEY = Fernet.generate_key()
BROWSER_A = "a" * 43
BROWSER_B = "b" * 43


@pytest.fixture(autouse=True)
def fernet_key(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_fernet_key() -> bytes:
        return KEY

    monkeypatch.setattr(crypto, "get_fernet_key", get_fernet_key)


def ctx(pre_auth_id: str | None) -> Any:
    return request_context_manager(RequestContext(pre_auth=PreAuth(id=pre_auth_id)))


def make_request(cookie: str | None = None, proto: str = "https") -> Request:
    headers = [(b"x-forwarded-proto", proto.encode())]
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    scope = {"type": "http", "path": "/", "headers": headers, "state": {}}
    return Request(scope)


@pytest.mark.anyio
async def test_roundtrip_returns_data() -> None:
    async with ctx(BROWSER_A):
        state = await preauth.create_login_state("sso", {"provider": "google"})
        assert await preauth.verify_login_state(state, "sso") == {"provider": "google"}


@pytest.mark.anyio
async def test_creates_id_for_new_browser() -> None:
    pre_auth = PreAuth()
    async with request_context_manager(RequestContext(pre_auth=pre_auth)):
        state = await preauth.create_login_state("sso")
    assert pre_auth.created and pre_auth.id
    async with ctx(pre_auth.id):
        await preauth.verify_login_state(state, "sso")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("verify_id", "purpose", "tamper", "max_age"),
    [
        (BROWSER_B, "sso", False, 600),  # another browser (login CSRF)
        (None, "sso", False, 600),  # no cookie
        (BROWSER_A, "other", False, 600),  # another flow
        (BROWSER_A, "sso", True, 600),  # forged token
        (BROWSER_A, "sso", False, -1),  # expired
    ],
)
async def test_rejects(
    verify_id: str | None, purpose: str, tamper: bool, max_age: int
) -> None:
    async with ctx(BROWSER_A):
        state = await preauth.create_login_state("sso")
    if tamper:
        state = state[:-6] + ("A" if state[-6] != "A" else "B") + state[-5:]
    async with ctx(verify_id):
        with pytest.raises(UnauthorizedException):
            await preauth.verify_login_state(state, purpose, max_age=max_age)


def test_cookie_set_only_when_created() -> None:
    request = make_request()
    request.state.user = None
    request.state.pre_auth = PreAuth()
    response = Response()
    preauth.apply_pre_auth_cookie(request, response)
    assert "set-cookie" not in response.headers

    request.state.pre_auth = PreAuth(id=BROWSER_A, created=True)
    preauth.apply_pre_auth_cookie(request, response)
    cookie = response.headers["set-cookie"]
    assert f"{preauth.COOKIE_NAME}={BROWSER_A}" in cookie
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie


def test_cookie_not_secure_on_http() -> None:
    request = make_request(proto="http")
    request.state.user = None
    request.state.pre_auth = PreAuth(id=BROWSER_A, created=True)
    response = Response()
    preauth.apply_pre_auth_cookie(request, response)
    assert "Secure" not in response.headers["set-cookie"]


def test_cookie_deleted_after_login() -> None:
    request = make_request(cookie=f"{preauth.COOKIE_NAME}={BROWSER_A}")
    request.state.user = object()
    request.state.pre_auth = preauth.pre_auth_from_request(request)
    response = Response()
    preauth.apply_pre_auth_cookie(request, response)
    assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.anyio
async def test_existing_id_refreshes_cookie() -> None:
    pre_auth = PreAuth(id=BROWSER_A)
    async with request_context_manager(RequestContext(pre_auth=pre_auth)):
        await preauth.create_login_state("sso")
    assert pre_auth.id == BROWSER_A and pre_auth.created


def test_cookie_flows_through_server_middlewares() -> None:
    """The handler sees the PreAuth set by AuthMiddleware, in the server's order."""
    from ayon_server.api.auth import AuthMiddleware
    from ayon_server.api.context import RequestContextMiddleware
    from ayon_server.api.server import app as server_app

    app = FastAPI()
    app.user_middleware = [
        m
        for m in server_app.user_middleware
        if m.cls in (AuthMiddleware, RequestContextMiddleware)  # type: ignore[comparison-overlap]
    ]

    @app.get("/state")
    async def state() -> str:
        return await preauth.create_login_state("sso", {"provider": "google"})

    @app.get("/verify")
    async def verify(state: str) -> dict[str, Any]:
        return await preauth.verify_login_state(state, "sso")

    client = TestClient(app, base_url="https://testserver")
    res = client.get("/state")
    assert preauth.COOKIE_NAME in res.cookies
    # The client sends the cookie back, as the browser does in the callback
    assert client.get("/verify", params={"state": res.json()}).json() == {
        "provider": "google"
    }


def test_malformed_cookie_ignored() -> None:
    request = make_request(cookie=f"{preauth.COOKIE_NAME}=short")
    assert preauth.pre_auth_from_request(request).id is None

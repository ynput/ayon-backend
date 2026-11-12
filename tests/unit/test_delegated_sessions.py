"""Sessions of applications: no IP binding, a fixed end, optional path limits."""

import time
from typing import Any

import pytest
from starlette.requests import Request

from ayon_server.api import auth as api_auth
from ayon_server.auth.session import DelegatedAccess, Session
from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import UnauthorizedException
from ayon_server.lib.redis import Redis
from ayon_server.utils import json_loads

IP_A = "1.1.1.1"
IP_B = "2.2.2.2"


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace Redis with a dict (keyed by namespace-key, like Redis)."""
    store: dict[str, Any] = {}

    async def get(namespace: str, key: str) -> Any:
        return store.get(f"{namespace}-{key}")

    async def get_json(namespace: str, key: str) -> Any:
        value = store.get(f"{namespace}-{key}")
        return None if value is None else json_loads(value)

    async def set(namespace: str, key: str, value: Any, ttl: int = 0) -> None:
        store[f"{namespace}-{key}"] = value

    async def delete(namespace: str, key: str) -> None:
        store.pop(f"{namespace}-{key}", None)

    async def incr(namespace: str, key: str, *, ttl: int = 0) -> int:
        store[f"{namespace}-{key}"] = store.get(f"{namespace}-{key}", 0) + 1
        return int(store[f"{namespace}-{key}"])

    async def iterate(namespace: str) -> Any:
        for key, value in list(store.items()):
            if key.startswith(f"{namespace}-"):
                yield key, value

    for name, func in {
        "get": get,
        "get_json": get_json,
        "set": set,
        "delete": delete,
        "incr": incr,
        "iterate": iterate,
    }.items():
        monkeypatch.setattr(Redis, name, func)
    return store


@pytest.fixture(autouse=True)
def events(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    dispatched: list[str] = []

    async def dispatch(topic: str, **kwargs: Any) -> None:
        dispatched.append(topic)

    monkeypatch.setattr(EventStream, "dispatch", dispatch)
    monkeypatch.setattr(ayonconfig, "trusted_proxy_hops", 1)
    monkeypatch.setattr(ayonconfig, "disable_check_session_ip", False)
    return dispatched


def make_user() -> UserEntity:
    return UserEntity(payload={"name": "artist"}, exists=False)


def make_request(ip: str, path: str = "/api/users/me", token: str = "") -> Request:
    headers = [(b"x-forwarded-for", ip.encode())]
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {
        "type": "http",
        "path": path,
        "query_string": b"",
        "headers": headers,
        "client": ("10.0.0.2", 1234),
    }
    return Request(scope)


def access(expires_in: float = 3600, paths: list[str] | None = None) -> DelegatedAccess:
    return DelegatedAccess(
        client_id="client",
        client_name="Some app",
        expires=time.time() + expires_in,
        paths=paths,
    )


@pytest.mark.parametrize(
    ("paths", "path", "allowed"),
    [
        (None, "/api/users/me", True),
        (["/api/mcp"], "/api/mcp", True),
        (["/api/mcp"], "/api/mcp/", True),
        (["/api/mcp/"], "/api/mcp", True),
        (["/api/mcp"], "/api/mcp/sub", True),
        (["/api/mcp"], "/api/mcpx", False),  # a prefix of the name is not below it
        (["/api/mcp"], "/api/users/me", False),
        (["/api/mcp", "/api/addons/mcp"], "/api/addons/mcp/1.0.0/mcp", True),
        # a * is any one segment: the MCP endpoint of every addon version,
        # not the addon's other endpoints
        (["/api/addons/mcp/*/mcp"], "/api/addons/mcp/1.0.0/mcp", True),
        (["/api/addons/mcp/*/mcp"], "/api/addons/mcp/1.0.0/mcp/sub", True),
        (["/api/addons/mcp/*/mcp"], "/api/addons/mcp/1.0.0/settings", False),
        (["/api/addons/mcp/*/mcp"], "/api/addons/mcp/1.0.0", False),
        (["/api/addons/mcp/*/mcp"], "/api/addons/mcp/a/b/mcp", False),
        (["/api/addons/mcp/*/mcp"], "/api/addons/other/1.0.0/mcp", False),
        ([], "/api/mcp", False),
    ],
)
def test_allows_path(paths: list[str] | None, path: str, allowed: bool) -> None:
    assert access(paths=paths).allows_path(path) is allowed


@pytest.mark.anyio
async def test_delegated_session_is_not_reported_as_login(events: list[str]) -> None:
    session = await Session.create(make_user(), make_request(IP_A), delegated=access())
    assert session.delegated is not None
    assert session.client_info is None
    assert not session.is_service
    await Session.delete(session.token)
    assert events == []


@pytest.mark.anyio
async def test_login_is_still_reported(events: list[str]) -> None:
    session = await Session.create(make_user(), make_request(IP_A))
    await Session.delete(session.token)
    assert events == ["auth.login", "auth.logout"]


@pytest.mark.anyio
async def test_delegated_session_cannot_take_a_given_token() -> None:
    with pytest.raises(ValueError):
        await Session.create(make_user(), token="x" * 64, delegated=access())


@pytest.mark.anyio
async def test_delegated_session_survives_an_ip_change() -> None:
    session = await Session.create(make_user(), delegated=access())
    assert await Session.check(session.token, make_request(IP_A)) is not None
    assert await Session.check(session.token, make_request(IP_B)) is not None


@pytest.mark.anyio
async def test_login_session_is_still_bound_to_its_ip() -> None:
    session = await Session.create(make_user(), make_request(IP_A))
    assert await Session.check(session.token, make_request(IP_A)) is not None
    assert await Session.check(session.token, make_request(IP_B)) is None


@pytest.mark.anyio
async def test_delegated_session_ends_at_its_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = await Session.create(make_user(), delegated=access(expires_in=60))
    now = time.time()
    # Used all along, which would keep a login alive
    monkeypatch.setattr(time, "time", lambda: now + 59)
    assert await Session.check(session.token, make_request(IP_A)) is not None
    monkeypatch.setattr(time, "time", lambda: now + 61)
    assert await Session.check(session.token, make_request(IP_A)) is None
    # and it is gone, not only refused
    monkeypatch.setattr(time, "time", lambda: now)
    assert await Session.check(session.token, make_request(IP_A)) is None


@pytest.mark.anyio
async def test_delegated_sessions_do_not_count_as_concurrent_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ayonconfig, "max_concurent_user_sessions", 1)
    user = make_user()
    login = await Session.create(user, make_request(IP_A))
    apps = [await Session.create(user, delegated=access()) for _ in range(3)]
    await Session.invalidate_least_used(user.name)
    assert await Session.check(login.token, make_request(IP_A)) is not None
    for app in apps:
        assert await Session.check(app.token, make_request(IP_A)) is not None


@pytest.mark.anyio
async def test_path_limited_session_is_refused_elsewhere() -> None:
    session = await Session.create(
        make_user(), delegated=access(paths=["/api/mcp", "/api/addons/mcp/*/mcp"])
    )
    token = session.token

    user = await api_auth.user_from_request(make_request(IP_A, "/api/mcp", token))
    assert user.name == "artist"
    request = make_request(IP_A, "/api/addons/mcp/1.0.0/mcp", token)
    assert (await api_auth.user_from_request(request)).name == "artist"

    for path in ("/api/users/me", "/graphql", "/api/mcpx"):
        with pytest.raises(UnauthorizedException):
            await api_auth.user_from_request(make_request(IP_A, path, token))

    # refused, not ended: it still works where it is allowed
    user = await api_auth.user_from_request(make_request(IP_B, "/api/mcp", token))
    assert user.name == "artist"


@pytest.mark.anyio
async def test_unlimited_delegated_session_works_everywhere() -> None:
    session = await Session.create(make_user(), delegated=access())
    for path in ("/api/users/me", "/graphql", "/api/mcp"):
        request = make_request(IP_A, path, session.token)
        assert (await api_auth.user_from_request(request)).name == "artist"


def refused_routes() -> dict[tuple[str, str], bool]:
    """{(method, path): refuses applications} of the account endpoints."""
    import importlib

    from fastapi.routing import APIRoute

    import ayon_server.api.server  # noqa: F401  (makes the API modules importable)
    from ayon_server.api.dependencies import NoDelegatedAccess

    result: dict[tuple[str, str], bool] = {}
    for module_name in ("auth", "users", "profile", "system"):
        router = importlib.import_module(module_name).router
        for route in router.routes:
            assert isinstance(route, APIRoute)
            refused = NoDelegatedAccess in route.dependencies
            for method in route.methods:
                result[(method, f"/api{route.path}")] = refused
    return result


@pytest.mark.parametrize(
    ("method", "path", "refused"),
    [
        # sessions, API keys, passwords, invites: no other way in
        ("POST", "/api/auth/sessions", True),
        ("GET", "/api/auth/sessions", True),
        ("GET", "/api/auth/tokenauth", True),
        ("POST", "/api/auth/logout", False),  # ending itself is fine
        ("POST", "/api/users/{user_name}/apikeys", True),
        ("PATCH", "/api/users/{user_name}/password", True),
        ("POST", "/api/users/{user_name}/invite", True),
        ("PATCH", "/api/users/{user_name}", True),
        ("PUT", "/api/users/{user_name}", True),
        ("DELETE", "/api/users/{user_name}", True),
        ("PATCH", "/api/users/{user_name}/accessGroups", True),
        ("GET", "/api/users/{user_name}/sessions", True),  # carries their tokens
        ("DELETE", "/api/users/{user_name}/sessions/{session_id}", True),
        ("PATCH", "/api/profile", True),  # the email a password reset goes to
        ("GET", "/api/secrets", True),
        ("GET", "/api/secrets/{secret_name}", True),
        ("PUT", "/api/secrets/{secret_name}", True),
        # reading users and working with everything else stays possible
        ("GET", "/api/users/{user_name}", False),
        ("GET", "/api/users/me", False),
        ("GET", "/api/users/{user_name}/apikeys", False),
        ("GET", "/api/profile", False),
        ("GET", "/api/info", False),
    ],
)
def test_what_an_application_is_refused(method: str, path: str, refused: bool) -> None:
    assert refused_routes()[(method, path)] is refused


# Open to anyone, so an application gains nothing there
PUBLIC_ACCOUNT_ROUTES = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/users/passwordResetRequest"),
    ("POST", "/api/users/passwordReset"),
    ("POST", "/api/users/acceptInvite"),
}


def test_new_account_endpoints_have_to_decide() -> None:
    """A change of accounts or secrets is refused, or listed as open above."""
    undecided = [
        f"{method} {path}"
        for (method, path), refused in refused_routes().items()
        if not refused
        and (method, path) not in PUBLIC_ACCOUNT_ROUTES
        and (
            path.startswith("/api/secrets")
            or (
                method not in ("GET", "HEAD", "OPTIONS")
                and path.startswith(("/api/users", "/api/profile", "/api/auth"))
                and path != "/api/auth/logout"
            )
        )
    ]
    assert undecided == []


@pytest.mark.anyio
async def test_application_does_not_see_the_users_secrets() -> None:
    user = UserEntity(
        payload={
            "name": "artist",
            "data": {
                "password": "hash:salt",
                "apiKeys": [{"key": "hashed"}],
                "inviteRequest": {"token": "t"},
                "isManager": True,
            },
        },
        exists=False,
    )
    app = await Session.create(user, delegated=access())
    seen = await api_auth.user_from_request(make_request(IP_A, token=app.token))
    assert seen.is_manager  # the user, with what they may do
    for key in ("password", "apiKeys", "inviteRequest"):
        assert key not in seen.data

    # a login is unchanged (an accepted invite is saved on login, hence no invite)
    del user.data["inviteRequest"]
    login = await Session.create(user, make_request(IP_A))
    seen = await api_auth.user_from_request(make_request(IP_A, token=login.token))
    assert seen.data["password"] == "hash:salt"


def test_application_is_refused_by_the_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whatever an endpoint checks itself, the request does not reach it."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ayon_server.api.auth import AuthMiddleware
    from ayon_server.api.context import RequestContextMiddleware
    from ayon_server.api.dependencies import NoDelegatedAccess
    from ayon_server.api.logging import LoggingMiddleware
    from ayon_server.api.server import app as server_app

    sessions: dict[str, Any] = {}

    async def user_from_request(request: Request) -> Any:
        if "x-test-session" not in request.headers:
            raise UnauthorizedException("Access token is missing")
        user = make_user()
        user.add_session(sessions[request.headers["x-test-session"]])
        return user

    monkeypatch.setattr(api_auth, "user_from_request", user_from_request)

    # LoggingMiddleware turns the server's exceptions into responses
    middlewares = (AuthMiddleware, LoggingMiddleware, RequestContextMiddleware)
    app = FastAPI()
    app.user_middleware = [
        m
        for m in server_app.user_middleware
        if m.cls in middlewares  # type: ignore[comparison-overlap]
    ]
    reached: list[str] = []

    # no current user asked for: the dependency does not rely on it
    @app.post("/api/auth/sessions", dependencies=[NoDelegatedAccess])
    async def create_session() -> str:
        reached.append("sessions")
        return "created"

    @app.get("/api/users/artist")
    async def get_user() -> str:
        return "artist"

    class FakeSession:
        def __init__(self, delegated: DelegatedAccess | None) -> None:
            self.token = "t" * 64
            self.is_api_key = False
            self.client_info = None
            self.delegated = delegated

    sessions["app"] = FakeSession(access())
    sessions["login"] = FakeSession(None)
    client = TestClient(app)

    res = client.post("/api/auth/sessions", headers={"x-test-session": "app"})
    assert res.status_code == 403 and reached == []
    res = client.get("/api/users/artist", headers={"x-test-session": "app"})
    assert res.status_code == 200
    res = client.post("/api/auth/sessions", headers={"x-test-session": "login"})
    assert res.status_code == 200 and reached == ["sessions"]
    # nobody logged in: left to the endpoint
    assert client.post("/api/auth/sessions").status_code == 200


@pytest.mark.anyio
async def test_delegated_session_is_dropped_from_the_store_at_its_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifetimes: list[int] = []

    async def set(namespace: str, key: str, value: Any, ttl: int = 0) -> None:
        lifetimes.append(ttl)

    monkeypatch.setattr(Redis, "set", set)
    await Session.create(make_user(), delegated=access(expires_in=600))
    await Session.create(make_user(), make_request(IP_A))
    assert 599 <= lifetimes[0] <= 602  # kept only as long as it is valid
    assert lifetimes[1] == 0  # a login is kept until it is unused for too long

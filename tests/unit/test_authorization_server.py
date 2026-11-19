"""The authorization server addon: /api/oauth, /.well-known and the 401 header."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ayon_server.addons.library import AddonLibrary
from ayon_server.auth import authorization_server as authsrv
from ayon_server.exceptions import UnauthorizedException

CHALLENGE = (
    'Bearer resource_metadata="https://ayon/.well-known/oauth-protected-resource"'
)


class FakeServer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def handle_request(self, request: Request, path: str) -> Response:
        return JSONResponse({"path": path, "method": request.method})

    async def handle_well_known(self, request: Request, path: str) -> Response | None:
        if path == "oauth-authorization-server":
            return JSONResponse({"issuer": "https://ayon"})
        return None

    async def get_challenge(self, request: Request) -> str | None:
        if self.fail:
            raise RuntimeError("broken addon")
        return CHALLENGE


class FakeAddon:
    def __init__(self, server: Any) -> None:
        self.authorization_server = server


class Queries:
    count = 0


def use_library(
    monkeypatch: pytest.MonkeyPatch,
    addons: dict[str, dict[str, Any]],
    production: str | None,
) -> Queries:
    """An AddonLibrary of these {addon name: {version: addon}}.

    The production bundle selects the `production` version of each.
    """
    from ayon_server.addons import library as library_module

    queries = Queries()

    async def fetch(query: str, *args: Any) -> list[dict[str, Any]]:
        queries.count += 1
        if production is None:
            return []
        bundle = {"name": "prod", "is_production": True, "is_staging": False}
        selected = dict.fromkeys(addons, production)
        return [{**bundle, "is_dev": False, "addons": selected}]

    library = AddonLibrary.__new__(AddonLibrary)
    library.data = addons  # type: ignore[assignment]
    library._active_versions = None
    monkeypatch.setattr(library_module.Postgres, "fetch", fetch)
    monkeypatch.setattr(AddonLibrary, "_instance", library)
    return queries


def make_request() -> Request:
    return Request({"type": "http", "path": "/api/users/me", "headers": []})


@pytest.mark.anyio
async def test_no_addon_no_server(monkeypatch: pytest.MonkeyPatch) -> None:
    queries = use_library(monkeypatch, {}, None)
    assert await authsrv.get_authorization_server() is None
    assert await authsrv.get_bearer_challenge(make_request()) is None
    assert queries.count == 0  # not installed: the database is not asked


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("addons", "production"),
    [
        ({"oauth": {"1.0.0": FakeAddon(FakeServer())}}, None),  # not in production
        ({"oauth": {"1.0.0": FakeAddon(FakeServer())}}, "2.0.0"),  # failed to load
        ({"oauth": {"1.0.0": FakeAddon(object())}}, "1.0.0"),  # not a server
        ({"oauth": {"1.0.0": object()}}, "1.0.0"),  # no such attribute
    ],
)
async def test_unusable_addon_is_no_server(
    monkeypatch: pytest.MonkeyPatch,
    addons: dict[str, dict[str, Any]],
    production: str | None,
) -> None:
    use_library(monkeypatch, addons, production)
    assert await authsrv.get_authorization_server() is None


@pytest.mark.anyio
async def test_production_addon_is_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer()
    addons = {"oauth": {"1.0.0": FakeAddon(server)}}
    queries = use_library(monkeypatch, addons, "1.0.0")
    assert await authsrv.get_authorization_server() is server
    assert await authsrv.get_bearer_challenge(make_request()) == CHALLENGE
    assert queries.count == 1  # the versions of the bundles are kept for a moment

    # until a bundle changes
    AddonLibrary.clear_active_versions_cache()
    assert await authsrv.get_authorization_server() is server
    assert queries.count == 2


@pytest.mark.anyio
async def test_failing_addon_gives_no_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    addons = {"oauth": {"1.0.0": FakeAddon(FakeServer(fail=True))}}
    use_library(monkeypatch, addons, "1.0.0")
    monkeypatch.setattr(authsrv, "log_traceback", lambda *args, **kwargs: None)
    assert await authsrv.get_bearer_challenge(make_request()) is None


def make_app() -> TestClient:
    """The server's own routes and middleware, without its startup."""
    from ayon_server.api.auth import AuthMiddleware
    from ayon_server.api.context import RequestContextMiddleware
    from ayon_server.api.dependencies import CurrentUser
    from ayon_server.api.logging import LoggingMiddleware
    from ayon_server.api.server import app as server_app
    from ayon_server.api.server import well_known

    middlewares = (AuthMiddleware, LoggingMiddleware, RequestContextMiddleware)
    app = FastAPI()
    app.user_middleware = [
        m
        for m in server_app.user_middleware
        if m.cls in middlewares  # type: ignore[comparison-overlap]
    ]
    app.add_api_route("/.well-known/{path:path}", well_known, methods=["GET"])
    # API modules are importable once the server loaded them
    import oauth_server  # type: ignore[import-not-found]

    app.include_router(oauth_server.router, prefix="/api")

    @app.get("/protected")
    async def protected(user: CurrentUser) -> str:
        return user.name

    @app.get("/own-challenge")
    async def own_challenge() -> Response:
        return Response(status_code=401, headers={"WWW-Authenticate": "Basic"})

    return TestClient(app)


@pytest.fixture
def no_session(monkeypatch: pytest.MonkeyPatch) -> None:
    from ayon_server.api import auth as api_auth

    async def user_from_request(request: Request) -> Any:
        raise UnauthorizedException("Access token is missing")

    monkeypatch.setattr(api_auth, "user_from_request", user_from_request)


def test_without_addon_nothing_answers(
    monkeypatch: pytest.MonkeyPatch, no_session: None
) -> None:
    use_library(monkeypatch, {}, None)
    client = make_app()

    res = client.get("/.well-known/oauth-authorization-server")
    assert res.status_code == 404
    assert res.headers["content-type"] == "application/json"

    assert client.post("/api/oauth/token").status_code == 404

    res = client.get("/protected")
    assert res.status_code == 401
    assert "www-authenticate" not in res.headers


def test_with_addon(monkeypatch: pytest.MonkeyPatch, no_session: None) -> None:
    addons = {"oauth": {"1.0.0": FakeAddon(FakeServer())}}
    use_library(monkeypatch, addons, "1.0.0")
    client = make_app()

    res = client.get("/.well-known/oauth-authorization-server")
    assert res.json() == {"issuer": "https://ayon"}
    # a document the addon does not have is a 404, not the web interface
    assert client.get("/.well-known/security.txt").status_code == 404

    # passed on with its method and path, not redirected
    res = client.post("/api/oauth/token", follow_redirects=False)
    assert res.json() == {"path": "token", "method": "POST"}
    res = client.get("/api/oauth/authorize/decision")
    assert res.json() == {"path": "authorize/decision", "method": "GET"}

    res = client.get("/protected")
    assert res.status_code == 401
    assert res.headers["www-authenticate"] == CHALLENGE

    # a handler's own challenge is kept
    assert client.get("/own-challenge").headers["www-authenticate"] == "Basic"

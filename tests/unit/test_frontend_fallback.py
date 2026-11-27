"""Frontend is the router default, so routes added after it still win."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ayon_server.api import frontend
from ayon_server.api.server import not_found_handler
from ayon_server.config import ayonconfig


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "remoteEntry.js").write_text("remote")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("app")
    monkeypatch.setattr(ayonconfig, "frontend_dir", str(tmp_path))
    frontend.get_index.cache_clear()

    app = FastAPI(redirect_slashes=False)
    app.add_exception_handler(404, not_found_handler)
    app.get("/api/thing")(lambda: {"ok": True})
    frontend.init_frontend(app)
    with TestClient(app) as client:
        client.app_ = app  # type: ignore[attr-defined]
        yield client
    frontend.get_index.cache_clear()


def test_deep_link_serves_index(client: TestClient) -> None:
    for path in ("/", "/projects/foo", "/index.html"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert res.text == "<html>spa</html>"
        assert res.headers["cache-control"] == "no-cache"


def test_static_files(client: TestClient) -> None:
    res = client.get("/assets/app.js")
    assert res.status_code == 200 and res.text == "app"
    assert "cache-control" not in res.headers
    res = client.get("/remoteEntry.js")
    assert res.text == "remote" and res.headers["cache-control"] == "no-cache"


def test_api_and_addons_404_are_json(client: TestClient) -> None:
    assert client.get("/api/thing").json() == {"ok": True}
    for path in ("/api/nope", "/addons/nope", "/api/thing/"):
        res = client.get(path)
        assert res.status_code == 404, path
        assert res.json()["path"] == path


def test_wrong_method_is_405(client: TestClient) -> None:
    assert client.delete("/api/thing").status_code == 405


def test_route_added_after_frontend(client: TestClient) -> None:
    assert client.get("/api/late").status_code == 404
    client.app_.get("/api/late")(lambda: {"late": True})  # type: ignore[attr-defined]
    assert client.get("/api/late").json() == {"late": True}
    assert client.get("/projects/foo").text == "<html>spa</html>"


def test_unmatched_websocket_is_closed(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/nope"):
            pass

"""Loading addon versions installed after startup (hot-load)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ayon_server.addons.library import AddonLibrary
from ayon_server.api import lifespan
from ayon_server.background import replica_heartbeat
from ayon_server.exceptions import AyonException

pytestmark = pytest.mark.anyio

SERVER = """
from ayon_server.addons import BaseServerAddon


class Addon(BaseServerAddon):
    def initialize(self):
        self.add_endpoint("hello", self.hello, method="GET")

    async def hello(self):
        return {{"version": self.version}}

    def setup(self):
        {setup}
"""


def make_addon(
    root: Path, name: str, version: str, setup: str = "pass", legacy: bool = False
) -> None:
    vdir = root / name / version
    if legacy:
        vdir.mkdir(parents=True)
        (vdir / "__init__.py").write_text("")
        return
    (vdir / "server").mkdir(parents=True)
    (vdir / "package.py").write_text(f"name = {name!r}\nversion = {version!r}\n")
    (vdir / "server" / "__init__.py").write_text(SERVER.format(setup=setup))


@pytest.fixture
def addons_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(AddonLibrary, "get_addons_dir", lambda self: str(tmp_path))
    monkeypatch.setattr(AddonLibrary, "_instance", None)

    async def no_redis() -> None:
        AddonLibrary.clear_active_versions_cache()

    monkeypatch.setattr(AddonLibrary, "clear_addon_list_cache", no_redis)
    make_addon(tmp_path, "foo", "1.0.0")
    yield tmp_path


@pytest.fixture
def app(addons_dir: Path) -> FastAPI:
    app = FastAPI()
    lifespan.init_addon_endpoints(app)
    return app


async def test_new_version_of_existing_addon(addons_dir: Path, app: FastAPI) -> None:
    make_addon(addons_dir, "foo", "1.1.0")
    await lifespan.load_addon_version(app, "foo", "1.1.0")

    definition = AddonLibrary.getinstance()["foo"]
    assert list(definition.versions) == ["1.0.0", "1.1.0"]
    client = TestClient(app)
    assert client.get("/api/addons/foo/1.1.0/hello").json() == {"version": "1.1.0"}
    assert client.get("/api/addons/foo/1.0.0/hello").json() == {"version": "1.0.0"}


async def test_older_version_is_sorted(addons_dir: Path, app: FastAPI) -> None:
    make_addon(addons_dir, "foo", "0.9.0")
    await lifespan.load_addon_version(app, "foo", "0.9.0")
    assert list(AddonLibrary.getinstance()["foo"].versions) == ["0.9.0", "1.0.0"]


async def test_completely_new_addon(addons_dir: Path, app: FastAPI) -> None:
    make_addon(addons_dir, "bar", "2.0.0")
    await lifespan.load_addon_version(app, "bar", "2.0.0")
    assert "bar" in AddonLibrary.getinstance()
    res = TestClient(app).get("/api/addons/bar/2.0.0/hello")
    assert res.json() == {"version": "2.0.0"}


async def test_idempotent(addons_dir: Path, app: FastAPI) -> None:
    make_addon(addons_dir, "foo", "1.1.0")
    await lifespan.load_addon_version(app, "foo", "1.1.0")
    routes = len(app.router.routes)
    await lifespan.load_addon_version(app, "foo", "1.1.0")
    assert len(app.router.routes) == routes


@pytest.mark.parametrize(
    "setup",
    ["raise RuntimeError('boom')", "self.request_server_restart()"],
)
async def test_failure_unloads(addons_dir: Path, app: FastAPI, setup: str) -> None:
    make_addon(addons_dir, "foo", "1.1.0", setup=setup)
    routes = len(app.router.routes)
    with pytest.raises(AyonException):
        await lifespan.load_addon_version(app, "foo", "1.1.0")
    assert "1.1.0" not in AddonLibrary.getinstance()["foo"].versions
    assert AddonLibrary.is_broken("foo", "1.1.0")
    assert len(app.router.routes) == routes


async def test_failure_in_heartbeat(
    addons_dir: Path, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_addon(addons_dir, "foo", "1.1.0", setup="raise RuntimeError('boom')")
    with pytest.raises(AyonException):
        await lifespan.load_addon_version(app, "foo", "1.1.0")

    monkeypatch.setattr(replica_heartbeat, "is_ready", lambda: True)
    info = replica_heartbeat.ReplicaHeartbeat().get_info()
    assert info.addons["foo"] == ["1.0.0"]
    assert info.broken == {"foo": {"1.1.0": "boom"}}


async def test_legacy_rejected(addons_dir: Path, app: FastAPI) -> None:
    make_addon(addons_dir, "foo", "1.1.0", legacy=True)
    with pytest.raises(AssertionError):
        await lifespan.load_addon_version(app, "foo", "1.1.0")

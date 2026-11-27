"""A new addon version is loaded live, a replaced one needs a restart."""

import zipfile
from pathlib import Path
from typing import Any

import pytest

from ayon_server import installer
from ayon_server.config import ayonconfig
from ayon_server.installer.addons import AddonZipInfo, unpack_addon_sync

pytestmark = pytest.mark.anyio


def make_zip(path: Path) -> AddonZipInfo:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("addon/package.py", "name = 'foo'\nversion = '1.0.0'\n")
    return AddonZipInfo(name="foo", version="1.0.0", zip_path=str(path))


def test_unpack_reports_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ayonconfig, "addons_dir", str(tmp_path / "addons"))
    assert unpack_addon_sync(make_zip(tmp_path / "a.zip")) is False
    assert unpack_addon_sync(make_zip(tmp_path / "b.zip")) is True
    assert (tmp_path / "addons" / "foo" / "1.0.0" / "package.py").is_file()


@pytest.mark.parametrize(
    "replaced, hot_load", [(False, True), (True, False), (None, False)]
)
async def test_activate_addon(
    monkeypatch: pytest.MonkeyPatch, replaced: bool | None, hot_load: bool
) -> None:
    dispatched: list[tuple[str, dict[str, Any]]] = []

    async def dispatch(topic: str, **kwargs: Any) -> str:
        dispatched.append((topic, kwargs["summary"]))
        return "id"

    monkeypatch.setattr(installer.EventStream, "dispatch", dispatch)
    worker = installer.BackgroundInstaller()
    await worker.activate_addon(AddonZipInfo(name="foo", version="1.0.0"), replaced)

    if hot_load:
        assert dispatched == [("addon.hot_load", {"name": "foo", "version": "1.0.0"})]
        assert not worker.restart_needed
    else:
        assert dispatched == []
        assert worker.restart_needed

import pytest
from fastapi.exceptions import FastAPIDeprecationWarning
from pydantic.warnings import PydanticDeprecatedSince20

from ayon_server import deprecations
from ayon_server.deprecations import (
    AyonDeprecationWarning,
    is_addon_path,
    is_deprecation,
    split_addon_path,
)


@pytest.fixture
def addons_dir(monkeypatch):
    monkeypatch.setattr(deprecations, "_addons_dir", "/addons/")


class TestIsDeprecation:
    @pytest.mark.parametrize(
        "category",
        [
            DeprecationWarning,
            AyonDeprecationWarning,
            PydanticDeprecatedSince20,
            FastAPIDeprecationWarning,
        ],
    )
    def test_deprecation_categories(self, category):
        assert is_deprecation(category, "whatever")

    def test_pydantic_v2_migration_user_warning(self):
        message = "Valid config keys have changed in V2:\n* 'orm_mode' ..."
        assert is_deprecation(UserWarning, message)

    def test_other_warnings(self):
        assert not is_deprecation(UserWarning, "Something happened")
        assert not is_deprecation(RuntimeWarning, "coroutine was never awaited")


@pytest.mark.usefixtures("addons_dir")
class TestAddonPath:
    def test_split_addon_path(self):
        assert split_addon_path("/addons/core/1.2.3/server/settings/main.py") == (
            "/addons/core",
            "1.2.3",
            "server/settings/main.py",
        )

    def test_addon_dir_itself(self):
        assert split_addon_path("/addons/core/1.2.3/") == ("/addons/core", "1.2.3", "")

    @pytest.mark.parametrize(
        "path",
        [
            "/backend/ayon_server/logging.py",
            "/addons_backup/core/1.2.3/server/main.py",
            "/addons/core/shared.py",
        ],
    )
    def test_not_addon_path(self, path):
        assert split_addon_path(path) is None
        assert not is_addon_path(path)

    def test_missing_addons_dir(self, monkeypatch):
        monkeypatch.setattr(deprecations, "_addons_dir", None)
        monkeypatch.setattr(deprecations, "get_addons_dir", lambda: None)
        assert split_addon_path("/addons/core/1.2.3/server/main.py") is None

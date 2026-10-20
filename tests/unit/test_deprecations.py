import warnings

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


class TestNxtools:
    def _run(self, code: str) -> list[warnings.WarningMessage]:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            exec(compile(code, "/addons/foo/1.0.0/server/main.py", "exec"), {})
        return caught

    def test_from_import_warns_at_caller(self):
        caught = self._run("from nxtools import logging, slugify")
        assert [w.category for w in caught] == [AyonDeprecationWarning] * 2
        assert {w.filename for w in caught} == {"/addons/foo/1.0.0/server/main.py"}
        assert "from ayon_server.logging import logger" in str(caught[0].message)

    def test_attribute_access_warns(self):
        caught = self._run("import nxtools\nnxtools.slugify('a')")
        assert len(caught) == 1
        assert caught[0].lineno == 2

    def test_returns_replacement(self):
        from ayon_server.utils.strings import slugify

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from nxtools import slugify as nx_slugify

        assert nx_slugify is slugify

    def test_unknown_attribute(self):
        import nxtools

        with pytest.raises(AttributeError):
            nxtools.nope  # noqa: B018

"""Bundle models.

The `data` column of the bundles table is validated by `BundleDataModel`,
`BundleModel` is its flat REST representation (data + row columns)
and `BundlePatchModel` is used to update a bundle.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from api.bundles.models import (
    AddonDevelopmentItem,
    BundleDataModel,
    BundleModel,
    BundlePatchModel,
    DependencyPackagesModel,
)
from ayon_server.bundles import project_bundles
from ayon_server.entities import ProjectEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis

DATA_FIELDS = {
    "description",
    "is_project",
    "addons",
    "installer_version",
    "dependency_packages",
    "addon_development",
}

#
# DependencyPackagesModel
#


class TestDependencyPackages:
    def test_default(self):
        assert DependencyPackagesModel().root == {}

    def test_platforms(self):
        packages = DependencyPackagesModel({"windows": "win.zip", "linux": None})
        assert packages.root == {"windows": "win.zip", "linux": None}
        assert packages.model_dump() == {"windows": "win.zip", "linux": None}

    def test_unknown_platform(self):
        with pytest.raises(ValidationError):
            DependencyPackagesModel.model_validate({"amiga": "amiga.zip"})

    def test_field_accepts_dict(self):
        data = BundleDataModel(dependency_packages={"darwin": "mac.zip"})
        assert isinstance(data.dependency_packages, DependencyPackagesModel)
        assert data.model_dump()["dependency_packages"] == {"darwin": "mac.zip"}


#
# BundleDataModel
#


class TestBundleData:
    def test_empty_stored_data(self):
        data = BundleDataModel.model_validate({})
        assert data.description is None
        assert data.is_project is False
        assert data.addons == {}
        assert data.installer_version is None
        assert data.dependency_packages.root == {}
        assert data.addon_development == {}

    def test_legacy_stored_data(self):
        """Data stored before the model existed (snake_case keys)."""
        data = BundleDataModel.model_validate(
            {
                "addons": {"core": "1.0.0", "ftrack": None},
                "installer_version": "1.2.3",
                "dependency_packages": {"windows": "win.zip"},
                "is_project": True,
                "addon_development": {"core": {"enabled": True, "path": "/dev"}},
            }
        )
        assert data.addons == {"core": "1.0.0", "ftrack": None}
        assert data.installer_version == "1.2.3"
        assert data.dependency_packages.root == {"windows": "win.zip"}
        assert data.is_project is True
        assert data.addon_development == {
            "core": AddonDevelopmentItem(enabled=True, path="/dev")
        }

    def test_camel_case_input(self):
        data = BundleDataModel.model_validate(
            {"installerVersion": "1.2.3", "dependencyPackages": {"linux": "l.zip"}}
        )
        assert data.installer_version == "1.2.3"
        assert data.dependency_packages.root == {"linux": "l.zip"}

    def test_unknown_fields_are_dropped(self):
        data = BundleDataModel.model_validate({"addons": {}, "unknown": 1})
        assert "unknown" not in data.model_dump()

    def test_addon_versions(self):
        data = BundleDataModel(
            addons={
                "a": "None",
                "b": "__inherit__",
                "c": "__disable__",
                "d": "1.0.0",
                "e": None,
            }
        )
        assert data.addons == {
            "a": None,
            "b": "__inherit__",
            "c": "__disable__",
            "d": "1.0.0",
            "e": None,
        }

    def test_invalid_addon_version_is_kept(self):
        # Stored data must stay loadable: only a warning is logged
        data = BundleDataModel(addons={"core": "not-a-version"})
        assert data.addons == {"core": "not-a-version"}

    def test_dump_is_storable(self):
        dump = BundleDataModel(
            addons={"core": "1.0.0"},
            dependency_packages={"windows": "win.zip"},
            addon_development={"core": {"path": "/dev"}},
        ).model_dump(by_alias=False)
        assert set(dump) == DATA_FIELDS
        assert dump["dependency_packages"] == {"windows": "win.zip"}
        assert dump["addon_development"] == {"core": {"enabled": True, "path": "/dev"}}
        assert BundleDataModel.model_validate(dump).model_dump() == dump


#
# BundleModel
#


def bundle(**kwargs: Any) -> BundleModel:
    return BundleModel(name="test_bundle", **kwargs)


class TestBundle:
    def test_defaults(self):
        b = bundle()
        assert isinstance(b.created_at, datetime)
        assert isinstance(b.updated_at, datetime)
        assert b.description is None
        assert b.is_project is False
        assert not (b.is_production or b.is_staging or b.is_archived or b.is_dev)

    def test_invalid_name(self):
        with pytest.raises(ValidationError):
            BundleModel(name="invalid name!")

    def test_rest_dump(self):
        dump = bundle(
            description="Hello",
            dependency_packages={"linux": "l.zip"},
        ).model_dump(by_alias=True)
        assert dump["description"] == "Hello"
        assert dump["dependencyPackages"] == {"linux": "l.zip"}
        assert "updatedAt" in dump
        assert "createdAt" in dump
        assert "isProject" in dump

    def test_to_data(self):
        b = bundle(
            description="Hello",
            addons={"core": "1.0.0"},
            installer_version="1.2.3",
            dependency_packages={"windows": "win.zip"},
            addon_development={"core": {"path": "/dev"}},
            is_project=True,
            is_production=True,
            active_user="admin",
        )
        data = b.to_data()
        assert type(data) is BundleDataModel
        assert data.model_dump(by_alias=False) == {
            "description": "Hello",
            "is_project": True,
            "addons": {"core": "1.0.0"},
            "installer_version": "1.2.3",
            "dependency_packages": {"windows": "win.zip"},
            "addon_development": {"core": {"enabled": True, "path": "/dev"}},
        }

    def test_to_data_overrides_stored_data(self):
        stored = BundleDataModel(
            description="Old",
            addons={"core": "1.0.0"},
            installer_version="1.0.0",
        )
        data = bundle(addons={"core": "2.0.0"}, installer_version=None).to_data(stored)
        assert data.addons == {"core": "2.0.0"}
        assert data.installer_version is None
        assert data.description is None

    def test_from_stored_data(self):
        """Construct the bundle the same way bundle_actions does."""
        stored = BundleDataModel.model_validate(
            {
                "addons": {"core": "1.0.0"},
                "description": "Hello",
                "dependency_packages": {"linux": "l.zip"},
            }
        )
        b = BundleModel(
            **stored.model_dump(include=set(BundleDataModel.model_fields)),
            name="test_bundle",
        )
        assert b.addons == {"core": "1.0.0"}
        assert b.description == "Hello"
        assert b.dependency_packages.root == {"linux": "l.zip"}
        assert b.to_data() == stored


#
# BundlePatchModel
#


class TestBundlePatch:
    def test_empty(self):
        patch = BundlePatchModel()
        assert patch.get_changed_fields() == []
        assert patch.get_changes_description("b") == "Bundle 'b' has been updated."

    def test_description(self):
        patch = BundlePatchModel(description="Hello")
        assert patch.get_changed_fields() == ["description"]
        assert patch.get_changes_description("b") == (
            "Bundle 'b' has been updated with a new description."
        )

    def test_clear_description(self):
        """Explicit null clears the description, so it is a change."""
        patch = BundlePatchModel.model_validate({"description": None})
        assert "description" in patch.model_fields_set
        assert patch.get_changed_fields() == ["description"]
        assert "description" in patch.get_changes_description("b")

    def test_dependency_packages(self):
        patch = BundlePatchModel.model_validate(
            {"dependencyPackages": {"windows": "win.zip"}}
        )
        assert patch.dependency_packages is not None
        assert patch.dependency_packages.root == {"windows": "win.zip"}
        assert patch.get_changed_fields() == ["dependencyPackages"]

    def test_invalid_dependency_packages(self):
        with pytest.raises(ValidationError):
            BundlePatchModel.model_validate({"dependencyPackages": {"amiga": "a"}})

    def test_invalid_addon_version(self):
        with pytest.raises(ValidationError):
            BundlePatchModel(addons={"core": "not-a-version"})

    def test_changes_description(self):
        patch = BundlePatchModel(is_staging=True, description="Hello")
        assert patch.get_changes_description("b") == (
            "Bundle 'b' has been set as staging, and updated with a new description."
        )


#
# Project bundles
#


class FakeProject:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    async def save(self) -> None:
        pass


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Record queries of project_bundles instead of running them."""
    calls: dict[str, list[Any]] = {"execute": []}

    async def execute(query: str, *args: Any) -> None:
        calls["execute"].append((query, args))

    async def noop(*args: Any, **kwargs: Any) -> None:
        pass

    @asynccontextmanager
    async def transaction(*args: Any, **kwargs: Any):
        yield

    async def load(*args: Any, **kwargs: Any) -> FakeProject:
        return FakeProject()

    monkeypatch.setattr(Postgres, "execute", execute)
    monkeypatch.setattr(Postgres, "transaction", transaction)
    monkeypatch.setattr(Postgres, "set_project_schema", noop)
    monkeypatch.setattr(ProjectEntity, "load", load)
    monkeypatch.setattr(Redis, "delete_ns", noop)
    return calls


def set_fetchrow(monkeypatch: pytest.MonkeyPatch, row: dict[str, Any] | None):
    async def fetchrow(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return row

    monkeypatch.setattr(Postgres, "fetchrow", fetchrow)


class TestProjectBundles:
    def test_freeze_does_not_overwrite_description(self, db):
        asyncio.run(
            project_bundles.freeze_project_bundle(
                "test_project",
                addons={},
                installer_version="1.2.3",
                dependency_packages={"windows": "win.zip"},
            )
        )
        [(query, (name, data))] = db["execute"]
        assert "bundles.data || EXCLUDED.data" in query
        assert "updated_at = NOW()" in query
        assert name == project_bundles.get_project_bundle_name(
            "test_project", "production"
        )
        # Unset fields (description, addon_development) are kept in the db
        assert data == {
            "addons": {},
            "installer_version": "1.2.3",
            "dependency_packages": {"windows": "win.zip"},
            "is_project": True,
        }

    @pytest.mark.parametrize(
        "row, expected",
        [
            (None, {}),
            ({"data": {}}, {}),
            (
                {"data": {"addons": {"core": "1.0.0", "x": None}}},
                {"core": "1.0.0", "x": None},
            ),
        ],
    )
    def test_studio_bundle_addons(self, monkeypatch, row, expected):
        set_fetchrow(monkeypatch, row)
        result = asyncio.run(project_bundles.get_studio_bundle_addons("production"))
        assert result == expected

    def test_project_bundle_addons(self, monkeypatch):
        set_fetchrow(monkeypatch, {"data": {"addons": {"core": "1.0.0"}}})
        result = asyncio.run(
            project_bundles.get_project_bundle_addons("test_project", "production")
        )
        assert result == {"core": "1.0.0"}

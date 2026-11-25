"""Updating existing users through the users import."""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import Request

from api.data_import.import_data import import_data
from api.data_import.models import UserExportImportModel
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException


def make_user(name: str, **data: Any) -> UserEntity:
    return UserEntity(payload={"name": name, "data": data}, exists=True)


@pytest.fixture
def saved() -> list[str]:
    return []


@pytest.fixture
def users(monkeypatch: pytest.MonkeyPatch, saved: list[str]) -> dict[str, UserEntity]:
    """Users the import loads, and records which of them were saved."""
    store = {
        "admin": make_user("admin", isAdmin=True),
        "other.admin": make_user("other.admin", isAdmin=True),
        "artist": make_user("artist"),
    }

    async def load(cls: type[UserEntity], name: str, **kwargs: Any) -> UserEntity:
        return store[name]

    async def save(self: UserEntity, *args: Any, **kwargs: Any) -> bool:
        saved.append(self.name)
        return True

    monkeypatch.setattr(UserEntity, "load", classmethod(load))
    monkeypatch.setattr(UserEntity, "save", save)
    return store


@pytest.mark.anyio
async def test_import_deactivates_user(
    users: dict[str, UserEntity], saved: list[str]
) -> None:
    await UserExportImportModel.update(
        user=users["admin"], name="artist", active=False, attrib={"fullName": "A"}
    )
    assert users["artist"].active is False
    assert users["artist"].attrib.fullName == "A"
    assert saved == ["artist"]


@pytest.mark.anyio
async def test_import_reactivates_user(users: dict[str, UserEntity]) -> None:
    users["artist"].active = False
    await UserExportImportModel.update(user=users["admin"], name="artist", active=True)
    assert users["artist"].active is True


@pytest.mark.anyio
async def test_import_without_active_keeps_it(users: dict[str, UserEntity]) -> None:
    users["artist"].active = False
    await UserExportImportModel.update(
        user=users["admin"], name="artist", attrib={"fullName": "A"}
    )
    assert users["artist"].active is False


@pytest.mark.anyio
async def test_import_preview_does_not_save(
    users: dict[str, UserEntity], saved: list[str]
) -> None:
    await UserExportImportModel.update(
        user=users["admin"], name="artist", active=False, preview=True
    )
    assert saved == []


@pytest.mark.anyio
async def test_import_follows_users_api_rules(users: dict[str, UserEntity]) -> None:
    # Admins cannot demote themselves, as in PATCH /api/users/{name}
    await UserExportImportModel.update(
        user=users["admin"], name="admin", data={"isAdmin": False}
    )
    assert users["admin"].is_admin

    # Only managers can modify other users
    with pytest.raises(ForbiddenException):
        await UserExportImportModel.update(
            user=users["artist"], name="other.admin", active=False
        )
    assert users["other.admin"].active is True


@pytest.mark.anyio
async def test_applications_cannot_import_users(users: dict[str, UserEntity]) -> None:
    # Same as the users API (NoDelegatedAccess)
    admin = users["admin"]
    admin.session = cast(
        Any, SimpleNamespace(delegated=SimpleNamespace(impersonator=None))
    )
    request = cast(Request, SimpleNamespace(state=SimpleNamespace(user=admin)))
    with pytest.raises(ForbiddenException):
        await import_data(
            request=request,
            import_type="user",
            user=admin,
            file_id="x",
            column_mapping=[],
        )

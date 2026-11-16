"""An administrator acting as another user."""

import time
from typing import Any

import pytest
from starlette.requests import Request

from ayon_server.api import auth as api_auth
from ayon_server.api.context import RequestContext, request_context_manager
from ayon_server.api.dependencies import (
    dep_no_application_access,
    dep_no_delegated_access,
)
from ayon_server.auth.session import DelegatedAccess, Session
from ayon_server.entities import UserEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.utils import json_loads


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
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

    for name, func in {
        "get": get,
        "get_json": get_json,
        "set": set,
        "delete": delete,
        "incr": incr,
    }.items():
        monkeypatch.setattr(Redis, name, func)
    return store


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    dispatched: list[tuple[str, dict[str, Any]]] = []

    async def dispatch(topic: str, **kwargs: Any) -> None:
        dispatched.append((topic, kwargs))

    monkeypatch.setattr(EventStream, "dispatch", dispatch)
    return dispatched


def make_user(name: str, **data: Any) -> UserEntity:
    return UserEntity(payload={"name": name, "data": data}, exists=True)


@pytest.fixture
def users(monkeypatch: pytest.MonkeyPatch) -> dict[str, UserEntity]:
    known = {
        "admin": make_user("admin", isAdmin=True),
        "artist": make_user(
            "artist",
            password="hash:salt",
            inviteRequest={"token": "t"},
        ),
    }

    async def load(name: str, *args: Any, **kwargs: Any) -> UserEntity:
        return known[name]

    monkeypatch.setattr(UserEntity, "load", load)
    return known


def make_request(token: str, path: str = "/api/users/me") -> Request:
    scope = {
        "type": "http",
        "path": path,
        "query_string": b"",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "client": ("10.0.0.2", 1234),
    }
    return Request(scope)


async def impersonate(admin: str, target: UserEntity) -> str:
    """A session of `target` that the administrator `admin` acts in."""
    session = await Session.create(
        target,
        delegated=DelegatedAccess(
            client_id="ayon-impersonation",
            client_name=f"{admin} acting as {target.name}",
            expires=time.time() + 3600,
            impersonator=admin,
        ),
    )
    return session.token


@pytest.mark.anyio
async def test_the_session_names_the_impersonator(
    users: dict[str, UserEntity], events: list[tuple[str, dict[str, Any]]]
) -> None:
    token = await impersonate("admin", users["artist"])

    seen = await api_auth.user_from_request(make_request(token))
    assert seen.name == "artist"
    assert seen.session and seen.session.delegated
    assert seen.session.delegated.impersonator == "admin"
    # whoever starts it reports it
    assert events == []


@pytest.mark.anyio
async def test_ending_it_is_recorded(
    users: dict[str, UserEntity], events: list[tuple[str, dict[str, Any]]]
) -> None:
    token = await impersonate("admin", users["artist"])
    await Session.delete(token)
    topic, kwargs = events[-1]
    assert topic == "auth.impersonate.end"
    assert kwargs["user"] == "admin"
    assert kwargs["summary"] == {"target": "artist"}


@pytest.mark.anyio
async def test_events_name_the_impersonator(
    monkeypatch: pytest.MonkeyPatch, users: dict[str, UserEntity]
) -> None:
    stored: list[tuple[Any, ...]] = []

    async def execute(query: str, *args: Any) -> str:
        stored.append(args)
        return "INSERT 0 1"

    async def publish(*args: Any, **kwargs: Any) -> None:
        pass

    monkeypatch.setattr(Postgres, "execute", execute)
    monkeypatch.setattr(Redis, "publish", publish)

    context = RequestContext(user=users["artist"], impersonator="admin")
    async with request_context_manager(context):
        await EventStream.dispatch("entity.task.status_changed", payload={"a": 1})
    async with request_context_manager(RequestContext(user=users["artist"])):
        await EventStream.dispatch("entity.task.status_changed", payload={"a": 1})

    # user_name, then payload
    assert stored[0][6] == "artist"
    assert stored[0][11] == {"a": 1, "impersonatedBy": "admin"}
    assert stored[1][11] == {"a": 1}


def request_of(session: Any) -> Any:
    user = make_user("artist")
    user.add_session(session)
    return type("FakeRequest", (), {"state": type("State", (), {"user": user})()})()


def delegated_session(impersonator: str | None) -> Any:
    class DelegatedSession:
        token = "t" * 64
        is_api_key = False
        client_info = None
        delegated = DelegatedAccess(
            client_id="ayon-impersonation" if impersonator else "app",
            client_name="admin acting as artist" if impersonator else "An app",
            expires=9e9,
            impersonator=impersonator,
        )

    return DelegatedSession()


@pytest.mark.anyio
async def test_accounts_and_credentials_are_refused() -> None:
    request = request_of(delegated_session("admin"))
    with pytest.raises(ForbiddenException, match="acting as another user"):
        await dep_no_delegated_access(request)


@pytest.mark.anyio
async def test_the_web_ui_may_save_its_preferences() -> None:
    # set_frontend_preferences takes NoApplicationAccess
    await dep_no_application_access(request_of(delegated_session("admin")))
    with pytest.raises(ForbiddenException, match="Applications"):
        await dep_no_application_access(request_of(delegated_session(None)))

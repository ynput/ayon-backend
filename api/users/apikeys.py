import time
from typing import Any

from ayon_server.api.dependencies import CurrentUser, PathEntityID, UserName
from ayon_server.auth.session import Session
from ayon_server.auth.utils import hash_password
from ayon_server.exceptions import BadRequestException, ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import OPModel
from ayon_server.utils import create_uuid

from .router import router


class ApiKeyModel(OPModel):
    id: str
    label: str
    preview: str
    created: float
    expires: float | None = None


class ApiKeyPostModel(OPModel):
    label: str
    key: str
    expires: float | None = None


class ApiKeyPatchModel(OPModel):
    label: str | None = None
    expires: float | None = None


async def get_api_key_records(user_name: str) -> list[dict[str, Any]]:
    query = "SELECT data->'apiKeys' as api_keys FROM users WHERE name = $1"
    res = await Postgres.fetch(query, user_name)
    if not res:
        return []
    # NULL for a user who never had a personal key
    return res[0]["api_keys"] or []


async def end_api_key_sessions(user_name: str, hashed_keys: set[str]) -> None:
    """End the sessions opened with the given (hashed) keys.

    The first request with a key caches a session under the key itself,
    and later requests use it without reading the database. Without this,
    a revoked key keeps working until that session expires.
    """
    if not hashed_keys:
        return
    async for session in Session.list(user_name):
        if session.is_api_key and hash_password(session.token) in hashed_keys:
            await Session.delete(session.token, message="API key revoked")


@router.get("/{user_name}/apikeys")
async def get_user_api_keys(
    current_user: CurrentUser,
    user_name: UserName,
) -> list[ApiKeyModel]:
    if not current_user.is_admin and current_user.name != user_name:
        raise ForbiddenException()
    records = await get_api_key_records(user_name)
    return [ApiKeyModel(**record) for record in records]


@router.post("/{user_name}/apikeys")
async def create_user_api_key(
    current_user: CurrentUser,
    payload: ApiKeyPostModel,
    user_name: UserName,
):
    if not current_user.is_admin and current_user.name != user_name:
        raise ForbiddenException()

    records = await get_api_key_records(user_name)
    new_id = create_uuid()
    if any(key["label"] == payload.label for key in records):
        raise BadRequestException("API key with this label already exists")

    new_key = hash_password(payload.key)
    new_key_pvw = payload.key[:4] + "*****" + payload.key[-4:]

    records.append(
        {
            "id": new_id,
            "label": payload.label,
            "key": new_key,
            "preview": new_key_pvw,
            "created": time.time(),
            "expires": payload.expires,
        }
    )

    query = "UPDATE users SET data = jsonb_set(data, '{apiKeys}', $1) WHERE name = $2"
    await Postgres.execute(query, records, user_name)

    return None


@router.patch("/{user_name}/apikeys/{entity_id}")
async def update_user_api_key(
    current_user: CurrentUser,
    payload: ApiKeyPatchModel,
    user_name: UserName,
    entity_id: PathEntityID,
) -> None:
    if not current_user.is_admin and current_user.name != user_name:
        raise ForbiddenException()

    records = await get_api_key_records(user_name)
    changed_expiry: set[str] = set()
    for key in records:
        if key["id"] == entity_id:
            if payload.label is not None:
                key["label"] = payload.label
            if payload.expires is not None:
                key["expires"] = payload.expires
                changed_expiry.add(key["key"])

    query = "UPDATE users SET data = jsonb_set(data, '{apiKeys}', $1) WHERE name = $2"
    await Postgres.execute(query, records, user_name)
    # the next request checks the new expiry
    await end_api_key_sessions(user_name, changed_expiry)


@router.delete("/{user_name}/apikeys/{entity_id}")
async def delete_user_api_key(
    current_user: CurrentUser,
    user_name: UserName,
    entity_id: PathEntityID,
) -> None:
    if not current_user.is_admin and current_user.name != user_name:
        raise ForbiddenException()

    records = await get_api_key_records(user_name)
    removed = {key["key"] for key in records if key["id"] == entity_id}
    records = [key for key in records if key["id"] != entity_id]

    query = "UPDATE users SET data = jsonb_set(data, '{apiKeys}', $1) WHERE name = $2"
    await Postgres.execute(query, records, user_name)
    await end_api_key_sessions(user_name, removed)

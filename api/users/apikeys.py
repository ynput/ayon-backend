from fastapi import Path

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import OPModel

from .router import router


class ApiKeyModel(OPModel):
    id: str
    label: str
    preview: str
    created: float
    expires: float | None


class ApiKeyPostModel(OPModel):
    label: str
    key: str
    expires: float | None


@router.get("/{user_name}/apikeys")
async def get_user_api_keys(current_user: CurrentUser, user_name: str = Path(...)):
    if not current_user.is_admin and current_user.name != user_name:
        raise ForbiddenException()

    query = "SELECT data->'apiKeys' FROM users WHERE name = $1"
    res = await Postgres.fetch(query, user_name)
    if not res:
        return []

    apikeys = res[0].get("apiKeys", [])

    return [ApiKeyModel(**key) for key in apikeys]


@router.post("/{user_name}/apikeys")
async def create_user_api_key(
    current_user: CurrentUser,
    payload: ApiKeyPostModel,
    user_name: str = Path(...),
):
    if not current_user.is_admin and current_user.name != user_name:
        raise ForbiddenException()

    return None


@router.delete("/{user_name}/apikeys/{api_key_id}")
async def delete_user_api_key(
    current_user: CurrentUser,
    user_name: str = Path(...),
    api_key_id: str = Path(...),
):
    if not current_user.is_admin and current_user.name != user_name:
        raise ForbiddenException()

    return None

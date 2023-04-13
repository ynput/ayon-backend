from fastapi import APIRouter, Depends, Response

from ayon_server.api import ResponseFactory
from ayon_server.api.dependencies import dep_current_user, dep_secret_name
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.secrets import Secrets
from ayon_server.types import OPModel

#
# Router
#

router = APIRouter(
    prefix="/secrets",
    tags=["Secrets"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)


class Secret(OPModel):
    name: str | None
    value: str | None


@router.get("", response_model_exclude_none=True)
async def get_list_of_secrets(
    user: UserEntity = Depends(dep_current_user),
) -> list[Secret]:

    if not user.is_manager:
        raise ForbiddenException

    result = []
    all_secrets = await Secrets.all()
    for name, value in all_secrets.items():
        val = value if user.is_admin else None
        result.append(Secret(name=name, value=val))
    return result


@router.get("/{secret_name}")
async def get_secret(
    user: UserEntity = Depends(dep_current_user),
    secret_name: str = Depends(dep_secret_name),
) -> Secret:
    """Return a secret value"""

    if not user.is_admin:
        raise ForbiddenException

    value = await Secrets.get(secret_name)
    if value is None:
        raise NotFoundException

    return Secret(name=secret_name, value=value)


@router.put("/{secret_name}")
async def save_secret(
    payload: Secret,
    user: UserEntity = Depends(dep_current_user),
    secret_name: str = Depends(dep_secret_name),
) -> Response:
    """Create or update a secret value"""

    if not user.is_admin:
        raise ForbiddenException

    await Secrets.set(secret_name, payload.value)
    return Response()


@router.delete("/{secret_name}")
async def delete_secret(
    user: UserEntity = Depends(dep_current_user),
    secret_name: str = Depends(dep_secret_name),
) -> Response:
    """Delete a secret"""

    if not user.is_admin:
        raise ForbiddenException

    await Secrets.delete(secret_name)
    return Response()

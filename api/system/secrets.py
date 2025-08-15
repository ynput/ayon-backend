from ayon_server.api.dependencies import CurrentUser, SecretName
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.secrets import Secrets
from ayon_server.types import Field, OPModel

from .router import router


class Secret(OPModel):
    name: str | None = Field(None, title="Secret name")
    value: str | None = Field(None, title="Secret value")


@router.get("/secrets", response_model_exclude_none=True)
async def get_list_of_secrets(user: CurrentUser) -> list[Secret]:
    """Return a list of stored secrets

    List all available secret names for managers,
    but only the values for the admin.
    """
    if not user.is_manager:
        raise ForbiddenException()

    result = []
    all_secrets = await Secrets.all()
    for name, value in all_secrets.items():
        val = value if user.is_admin else None
        if name.startswith("_"):
            # Skip internal secrets
            continue
        result.append(Secret(name=name, value=val))
    return result


@router.get("/secrets/{secret_name}")
async def get_secret(user: CurrentUser, secret_name: SecretName) -> Secret:
    """Return a secret value"""

    if not user.is_admin:
        raise ForbiddenException

    value = await Secrets.get(secret_name)
    if value is None:
        raise NotFoundException

    return Secret(name=secret_name, value=value)


@router.put("/secrets/{secret_name}", status_code=204)
async def save_secret(
    payload: Secret, user: CurrentUser, secret_name: SecretName
) -> EmptyResponse:
    """Create or update a secret value"""

    if not user.is_admin:
        raise ForbiddenException()

    if payload.value is None:
        raise BadRequestException("No value provided")

    await Secrets.set(secret_name, payload.value)
    return EmptyResponse()


@router.delete("/secrets/{secret_name}", status_code=204)
async def delete_secret(user: CurrentUser, secret_name: SecretName) -> EmptyResponse:
    """Delete a secret"""

    if not user.is_admin:
        raise ForbiddenException

    await Secrets.delete(secret_name)
    return EmptyResponse()

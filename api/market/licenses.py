from typing import Any

from fastapi import Query

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.cloud import CloudUtils

from .router import router


@router.get("/licenses")
async def get_licenses(
    user: CurrentUser,
    refresh: bool = Query(False),
) -> list[dict[str, Any]]:
    """Get list of licenses.

    This is a cloud-only endpoint.
    """

    if not user.is_admin:
        raise ForbiddenException("Only admins can access this endpoint")

    return await CloudUtils.get_licenses(refresh)

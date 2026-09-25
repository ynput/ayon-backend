from typing import Annotated, Any

from fastapi import Query

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.cloud import CloudUtils
from ayon_server.models import RestField, RestModel

from .router import router


class LicenseListModel(RestModel):
    licenses: Annotated[list[dict[str, Any]], RestField(default_factory=list)]
    synced_at: float | None = None


@router.get("/licenses")
async def get_licenses(
    user: CurrentUser,
    refresh: bool = Query(False),
) -> LicenseListModel:
    """Get list of licenses.

    This is a cloud-only endpoint.
    """

    if not user.is_admin:
        raise ForbiddenException("Only admins can access this endpoint")

    licenses = await CloudUtils.get_licenses(refresh)
    return LicenseListModel(licenses=licenses, synced_at=CloudUtils.licenses_synced_at)

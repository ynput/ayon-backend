from fastapi import APIRouter, Depends

from openpype.addons import AddonLibrary
from openpype.api import ResponseFactory, dep_current_user
from openpype.entities import UserEntity
from openpype.settings import BaseSettingsModel
from openpype.types import OPModel

router = APIRouter(
    tags=["Addon settings"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)


class GetProductionSettingsResponse(OPModel):
    settings: dict[str, BaseSettingsModel]
    versions: dict[str, str]


@router.get("/settings/production")
async def get_production_settings(
    user: UserEntity = Depends(dep_current_user),
):
    """Return all addon settings for the project."""

    library = AddonLibrary.getinstance()

    active_versions = await library.get_active_versions()

    result: dict[str, BaseSettingsModel] = {}
    versions: dict[str, str] = {}

    for addon_name, addon in library.items():
        if addon_name not in active_versions:
            continue
        try:
            production_version = active_versions[addon_name]["production"]
        except KeyError:
            continue

        try:
            active_addon = library.addon(addon_name, production_version)
        except Exception:
            continue

        settings = await active_addon.get_studio_settings()
        if settings is None:
            continue
        result[addon_name] = settings
        versions[addon_name] = production_version

    return GetProductionSettingsResponse(settings=result, versions=versions)

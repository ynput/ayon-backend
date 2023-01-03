from fastapi import Depends
from projects.router import router

from ayon_server.addons import AddonLibrary
from ayon_server.api import dep_current_user, dep_project_name
from ayon_server.entities import UserEntity
from ayon_server.settings import BaseSettingsModel
from ayon_server.types import OPModel


class GetProjectSettingsResponse(OPModel):
    settings: dict[str, BaseSettingsModel]
    versions: dict[str, str]


@router.get("/projects/{project_name}/settings")
async def get_project_settings(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
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

        print("PRODVER", addon_name, production_version)

        try:
            active_addon = library.addon(addon_name, production_version)
        except Exception:
            continue

        settings = await active_addon.get_project_settings(project_name)
        if settings is None:
            continue
        result[addon_name] = settings
        versions[addon_name] = production_version

    return GetProjectSettingsResponse(settings=result, versions=versions)

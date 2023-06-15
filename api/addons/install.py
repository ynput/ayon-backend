import zipfile

import aiofiles
import shortuuid
from fastapi import BackgroundTasks, Request

from ayon_server.dependencies import CurrentUser
from ayon_server.types import Field, OPModel

from .router import router


def get_zip_info(path: str) -> tuple[str, str]:
    """Returns the addon name and version from the zip file"""
    with zipfile.ZipFile(path, "r") as zip_ref:
        names = zip_ref.namelist()

    addon_name = None
    addon_version = None
    for path in names:
        path = path.strip("/").split("/")
        if len(path) < 2:
            continue
        _name, _version = path[:2]
        if addon_name is None:
            addon_name = _name
            addon_version = _version
            continue
        if _name != addon_name:
            raise RuntimeError("Multiple addon names found in zip file")
        if _version != addon_version:
            raise RuntimeError("Multiple addon versions found in zip file")

    if not (addon_name and addon_version):
        raise RuntimeError("No addon name or version found in zip file")

    return addon_name, addon_version


async def init_zip_install(background_tasks: BackgroundTasks, path: str) -> str:
    """Initiates addon installation from a zip file

    Ensures that the zip file is valid and contains a single addon,
    if not, raises an exception, otherwise starts the installation
    in the background and returns event ID of the installation process
    """

    addon_name, addon_version = get_zip_info(path)


#
# API
#


class InstallAddonResponseModel(OPModel):
    event_id: str = Field(..., title="Event ID")


@router.post("/addons/install")
async def upload_addon_zip_file(
    user: CurrentUser,
    request: Request,
    background_tasks: BackgroundTasks,
) -> InstallAddonResponseModel:
    temp_path = f"/tmp/{shortuuid.uuid()}.zip"

    async with aiofiles.open(temp_path, "wb") as f:
        async for chunk in request.stream():
            await f.write(chunk)

    event_id = await init_zip_install(background_tasks, temp_path)
    return InstallAddonResponseModel(event_id=event_id)


class InstallFromUrlRequestModel(OPModel):
    url: str = Field(..., title="URL to the addon zip file")


@router.post("/addons/install/from_url")
async def install_addon_from_url(
    user: CurrentUser,
    request: InstallFromUrlRequestModel,
    background_tasks: BackgroundTasks,
) -> InstallAddonResponseModel:
    return

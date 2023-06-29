import os

import aiofiles
from fastapi import Query, Request
from nxtools import logging

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import AyonException, ConflictException, ForbiddenException
from ayon_server.types import Field, OPModel, Platform

from .common import (
    BasePackageModel,
    SourceModel,
    SourcesPatchModel,
    get_desktop_dir,
    get_desktop_file_path,
    handle_download,
    handle_upload,
    iter_names,
    load_json_file,
)
from .router import router

#
# Models
#


class InstallerManifest(BasePackageModel):
    version: str = Field(
        ...,
        title="Version",
        description="Version of the installer",
        example="1.2.3",
    )
    python_version: str = Field(
        ...,
        title="Python version",
        description="Version of Python that the installer is created with",
        example="3.11",
    )
    python_modules: dict[str, str] = Field(
        default_factory=dict,
        title="Python modules",
        description="mapping of module_name:module_version used to create the installer",
        example={"requests": "2.25.1", "pydantic": "1.8.2"},
    )
    runtime_python_modules: dict[str, str] = Field(
        default_factory=dict,
        title="Runtime Python modules",
        description="mapping of module_name:module_version used to run the installer",
        example={"requests": "2.25.1", "pydantic": "1.8.2"},
    )

    @property
    def local_file_path(self) -> str:
        return get_desktop_file_path("installers", self.filename)

    @property
    def has_local_file(self) -> bool:
        return os.path.isfile(self.local_file_path)

    @property
    def path(self) -> str:
        return get_desktop_file_path("installers", f"{self.filename}.json")


class InstallerListModel(OPModel):
    installers: list[InstallerManifest] = Field(default_factory=list)


#
# Helpers
#


def get_manifest(filename: str) -> InstallerManifest:
    manifest_data = load_json_file("installers", f"{filename}.json")
    manifest = InstallerManifest(**manifest_data)
    if manifest.has_local_file:
        manifest.sources.append(SourceModel(type="server"))
    return manifest


#
# API
#


@router.get("/installers", response_model_exclude_none=True)
async def list_installers(
    user: CurrentUser,
    version: str | None = Query(None, description="Version of the package"),
    platform: Platform | None = Query(None, description="Platform of the package"),
) -> InstallerListModel:
    result: list[InstallerManifest] = []

    for filename in iter_names("installers"):
        try:
            manifest = get_manifest(filename)
        except Exception as e:
            logging.warning(f"Failed to load manifest file {filename}: {e}")
            continue

        if filename != manifest.filename:
            logging.warning(
                f"Filename in manifest does not match: {filename} != {manifest.filename}"
            )
            continue

        # Filtering

        if platform is not None and platform != manifest.platform:
            continue

        if version is not None and version != manifest.version:
            continue

        result.append(manifest)
    return InstallerListModel(installers=result)


@router.post("/installers", status_code=201)
async def create_installer(
    user: CurrentUser,
    payload: InstallerManifest,
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can create installers")

    try:
        _ = get_manifest(payload.filename)
    except Exception:
        pass
    else:
        raise ConflictException("Installer already exists")

    _ = get_desktop_dir("installers", for_writing=True)

    existing_installers = await list_installers(
        user=user,
        version=payload.version,
        platform=payload.platform,
    )
    if existing_installers.installers:
        raise AyonException(
            "Installer with the same version and platform already exists"
        )

    async with aiofiles.open(payload.path, "w") as f:
        await f.write(payload.json(exclude_none=True))

    return EmptyResponse(status_code=201)


@router.get("/installers/{filename}")
async def download_installer_file(user: CurrentUser, filename: str):
    installers_dir = get_desktop_dir("installers", for_writing=False)
    file_path = os.path.join(installers_dir, filename)
    return await handle_download(file_path)


@router.put("/installers/{filename}", status_code=204)
async def upload_installer_file(user: CurrentUser, request: Request, filename: str):
    if not user.is_admin:
        raise ForbiddenException("Only admins can upload installers")

    manifest = get_manifest(filename)

    if manifest.filename != filename:
        raise AyonException("Filename in manifest does not match")

    return await handle_upload(request, manifest.local_file_path)


@router.delete("/installers/{filename}", status_code=204)
async def delete_installer_file(user: CurrentUser, filename: str):
    if not user.is_admin:
        raise ForbiddenException("Only admins can delete installers")
    manifest = get_manifest(filename)
    if manifest.has_local_file:
        os.remove(manifest.local_file_path)
    os.remove(manifest.path)


@router.patch("/installers/{filename}", status_code=204)
async def patch_installer(user: CurrentUser, filename: str, payload: SourcesPatchModel):
    """Update sources for an installer"""
    if not user.is_admin:
        raise ForbiddenException("Only admins can patch installers")

    manifest = get_manifest(filename)

    if manifest.filename != filename:
        raise AyonException("Filename in manifest does not match")

    manifest.sources = payload.sources

    async with aiofiles.open(manifest.path, "w") as f:
        await f.write(manifest.json(exclude_none=True))

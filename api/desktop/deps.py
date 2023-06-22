import os

import aiofiles
from fastapi import Path, Request, Response
from nxtools import logging

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import AyonException, ForbiddenException
from ayon_server.types import Field, OPModel

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


class DependencyPackageManifest(BasePackageModel):
    installer_version: str = Field(
        ...,
        title="Installer version",
        description="Version of the Ayon installer that this dependency package is created with",
        example="1.2.3",
    )
    source_addons: dict[str, str] = Field(
        default_factory=dict,
        title="Source addons",
        description="mapping of addon_name:addon_version used to create the package",
        example={"ftrack": "1.2.3", "maya": "2.4"},
    )
    python_modules: dict[str, str] = Field(
        default_factory=dict,
        title="Python modules",
        description="mapping of module_name:module_version used to create the package",
        example={"requests": "2.25.1", "pydantic": "1.8.2"},
    )

    @property
    def local_file_path(self) -> str:
        return get_desktop_file_path("dependency_packages", self.filename)

    @property
    def has_local_file(self) -> bool:
        return os.path.isfile(self.local_file_path)

    @property
    def path(self) -> str:
        return get_desktop_file_path("dependency_packages", f"{self.filename}.json")


class DependencyPackageList(OPModel):
    packages: list[DependencyPackageManifest] = Field(default_factory=list)


#
# Helpers
#


def get_manifest(filename: str) -> DependencyPackageManifest:
    manifest_data = load_json_file("dependency_packages", f"{filename}.json")
    manifest = DependencyPackageManifest(**manifest_data)
    if manifest.has_local_file:
        print("dep has local file", manifest.local_file_path)
        manifest.sources.append(SourceModel(type="server"))
    return manifest


# TODO: add filtering
@router.get("/dependency_packages", response_model_exclude_none=True)
async def list_dependency_packages(user: CurrentUser) -> DependencyPackageList:
    """Return a list of dependency packages"""

    result: list[DependencyPackageManifest] = []
    for filename in iter_names("dependency_packages"):
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
        result.append(manifest)
    return DependencyPackageList(packages=result)


@router.post("/dependency_packages", status_code=204)
async def create_dependency_package(
    payload: DependencyPackageManifest,
    user: CurrentUser,
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can save dependency packages.")

    try:
        _ = get_manifest(payload.filename)
    except Exception:
        pass
    else:
        raise AyonException("Dependency package already exists")

    _ = get_desktop_dir("dependency_packages", for_writing=True)

    async with aiofiles.open(payload.path, "w") as f:
        await f.write(payload.json(exclude_none=True))
    return EmptyResponse()


@router.get("/dependency_packages/{filename}")
async def download_dependency_package(
    user: CurrentUser,
    filename: str = Path(...),
) -> Response:
    """Download dependency package.

    Use this endpoint to download dependency package stored on the server.
    """

    packages_dir = get_desktop_dir("dependency_packages", for_writing=False)
    file_path = os.path.join(packages_dir, filename)
    return await handle_download(file_path)


@router.put("/dependency_packages/{filename}", status_code=204)
async def upload_dependency_package(
    request: Request,
    user: CurrentUser,
    filename: str = Path(...),
) -> EmptyResponse:
    """Upload a dependency package to the server."""

    if not user.is_admin:
        raise ForbiddenException("Only admins can upload dependency packages.")

    manifest = get_manifest(filename)

    if manifest.filename != filename:
        raise AyonException("Filename in manifest does not match")

    await handle_upload(request, manifest.local_file_path)
    return EmptyResponse(status_code=204)


@router.delete("/dependency_packages/{filename}", status_code=204)
async def delete_dependency_package(
    user: CurrentUser,
    filename: str = Path(...),
) -> EmptyResponse:
    """Delete a dependency package from the server.
    If there is an uploaded package, it will be deleted as well.
    """

    if not user.is_admin:
        raise ForbiddenException("Only admins can delete dependency packages")

    manifest = get_manifest(filename)
    if manifest.has_local_file:
        os.remove(manifest.local_file_path)
    os.remove(manifest.path)

    return EmptyResponse()


@router.patch("/dependency_packages/{filename}", status_code=204)
async def update_dependency_package(
    payload: SourcesPatchModel,
    user: CurrentUser,
    filename: str = Path(...),
) -> EmptyResponse:
    """Update dependency package sources"""

    if not user.is_admin:
        raise ForbiddenException("Only admins can update dependency packages")

    manifest = get_manifest(filename)
    if manifest.filename != filename:
        raise AyonException("Filename in manifest does not match")

    manifest.sources = payload.sources
    async with aiofiles.open(manifest.path, "w") as f:
        await f.write(manifest.json(exclude_none=True))

    return EmptyResponse(status_code=204)

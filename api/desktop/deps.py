import hashlib
import os

import aiofiles
from fastapi import BackgroundTasks, Path, Query, Request, Response
from nxtools import logging

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.events import dispatch_event, update_event
from ayon_server.exceptions import (
    AyonException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.installer import background_installer
from ayon_server.installer.models import (
    DependencyPackageManifest,
    SourceModel,
    SourcesPatchModel,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .common import (
    InstallResponseModel,
    get_desktop_dir,
    get_desktop_file_path,
    handle_download,
    handle_upload,
    iter_names,
    load_json_file,
)
from .router import router


class DependencyPackage(DependencyPackageManifest):
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
    packages: list[DependencyPackage] = Field(default_factory=list)


#
# Helpers
#


def get_manifest(filename: str) -> DependencyPackage:
    try:
        manifest_data = load_json_file("dependency_packages", f"{filename}.json")
        manifest = DependencyPackage(**manifest_data)
    except FileNotFoundError:
        raise NotFoundException(f"Dependency package manifest {filename} not found")
    except ValueError:
        raise AyonException(f"Failed to load dependency package manifest {filename}")
    if manifest.has_local_file:
        if "server" not in [s.type for s in manifest.sources]:
            manifest.sources.append(SourceModel(type="server"))
    return manifest


# TODO: add filtering
@router.get("/dependency_packages", response_model_exclude_none=True, deprecated=True)
@router.get("/dependencyPackages", response_model_exclude_none=True)
async def list_dependency_packages(user: CurrentUser) -> DependencyPackageList:
    """Return a list of dependency packages"""

    result: list[DependencyPackage] = []
    for filename in iter_names("dependency_packages"):
        try:
            manifest = get_manifest(filename)
        except Exception as e:
            logging.warning(f"Failed to load manifest file {filename}: {e}")
            continue

        if filename != manifest.filename:
            logging.warning(
                "Filename in manifest does not match: "
                f"{filename} != {manifest.filename}"
            )
            continue
        result.append(manifest)
    return DependencyPackageList(packages=result)


@router.post("/dependency_packages", status_code=201, deprecated=True)
@router.post("/dependencyPackages", status_code=201)
async def create_dependency_package(
    background_tasks: BackgroundTasks,
    payload: DependencyPackage,
    user: CurrentUser,
    url: str | None = Query(None, title="URL to the addon zip file"),
    overwrite: bool = Query(False, title="Overwrite existing package"),
) -> InstallResponseModel:
    event_id: str | None = None

    if not user.is_admin:
        raise ForbiddenException("Only admins can save dependency packages.")

    try:
        _ = get_manifest(payload.filename)
    except Exception:
        pass
    else:
        if not overwrite:
            raise ConflictException(
                f"Dependency package {payload.filename} already exists"
            )

    _ = get_desktop_dir("dependency_packages", for_writing=True)

    async with aiofiles.open(payload.path, "w") as f:
        addons_to_delete = []
        for addon, version in payload.source_addons.items():
            if version is None:
                addons_to_delete.append(addon)
        if addons_to_delete:
            for addon in addons_to_delete:
                del payload.source_addons[addon]
        await f.write(payload.json(exclude_none=True))

    if url:
        hash = hashlib.sha256(f"dep_pkg_install_{url}".encode("utf-8")).hexdigest()

        query = """
            SELECT id FROM events
            WHERE topic = 'dependency_package.install_from_url'
            AND hash = $1
        """

        res = await Postgres.fetch(query, hash)
        if res:
            event_id = res[0]["id"]
            assert event_id
            await update_event(
                event_id,
                description="Reinstalling dependency package from URL",
                summary={"url": url},
                status="pending",
                retries=0,
            )
        else:
            event_id = await dispatch_event(
                "dependency_package.install_from_url",
                hash=hash,
                description="Installing dependency_package from URL",
                summary={"url": url},
                user=user.name,
                finished=False,
            )

        assert event_id
        background_tasks.add_task(background_installer.enqueue, event_id)

    return InstallResponseModel(event_id=event_id)


@router.get("/dependency_packages/{filename}", deprecated=True)
@router.get("/dependencyPackages/{filename}")
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


@router.put("/dependency_packages/{filename}", status_code=204, deprecated=True)
@router.put("/dependencyPackages/{filename}", status_code=204)
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


@router.delete("/dependency_packages/{filename}", status_code=204, deprecated=True)
@router.delete("/dependencyPackages/{filename}", status_code=204)
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


@router.patch("/dependency_packages/{filename}", status_code=204, deprecated=True)
@router.patch("/dependencyPackages/{filename}", status_code=204)
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

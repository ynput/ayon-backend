import os
from typing import Any, Literal

from fastapi import Path, Request, Response
from nxtools import logging

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import AyonException, ForbiddenException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils import dict_exclude

from .router import router

Platform = Literal["windows", "linux", "darwin"]


def md5sum(path: str) -> str:
    """Calculate md5sum of file."""
    import hashlib

    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def get_package_file_path(name: str, platform: Platform) -> str:
    """Get path to package file."""
    return f"/storage/dependency_packages/{name}-{platform}.zip"


class DependencyPackage(OPModel):
    """
    Each source is a dict with the type of the source as key and the value,
    the rest of the fields depend on the type of the source.

    type: "server" is added automatically by the server,
    if the package was uploaded to the server.
    """

    name: str = Field(..., description="Name of the package")
    platform: Platform = Field(..., description="Platform of the package")
    size: int = Field(..., description="Size of the package in bytes")

    checksum: str = Field(
        ...,
        title="Checksum",
        description="Checksum of the package",
    )
    checksum_algorithm: Literal["md5"] = Field(
        "md5",
        title="Checksum algorithm",
        description="Algorithm used to calculate the checksum",
    )
    supported_addons: dict[str, str] = Field(
        default_factory=dict,
        title="Supported addons",
        description="Supported addons and their versions {addon_name: version}",
    )
    python_modules: dict[str, str] = Field(
        default_factory=dict,
        description="Python modules {module_name: version} included in the package",
    )
    sources: list[dict[str, Any]] = Field(
        default_factory=list,
        title="Package sources",
        description="List of sources from which the package was downloaded",
        example=[
            {
                "type": "server",
                "filename": "win_ayon_package_1.0.0.zip",
            },
            {
                "type": "http",
                "url": "https://example.com/win_ayon_package_1.0.0.zip",
            },
        ],
    )


class DependencyPackageList(OPModel):
    packages: list[DependencyPackage] = Field(default_factory=list)
    production_package: str | None = None


@router.get("/dependency_packages")
async def list_dependency_packages() -> DependencyPackageList:
    """Return a list of dependency packages"""

    # TODO: is there a reason for not having authentication here?

    packages: list[DependencyPackage] = []
    async for row in Postgres.iterate(
        "SELECT * FROM dependency_packages ORDER BY name ASC"
    ):
        data = row["data"]
        if os.path.exists(
            file_path := get_package_file_path(row["name"], row["platform"])
        ):
            local_source = {
                "type": "server",
                "filename": os.path.basename(file_path),
            }
            data["sources"].append(local_source)

        packages.append(
            DependencyPackage(name=row["name"], platform=row["platform"], **data)
        )

    production_package = None
    if packages:
        production_package = packages[-1].name

    result = DependencyPackageList(
        packages=packages, production_package=production_package
    )
    return result


@router.post("/dependency_packages", status_code=204)
async def create_dependency_package(
    payload: DependencyPackage,
    user: CurrentUser,
) -> EmptyResponse:
    """Create (or update) a dependency package record in the database.

    You can set external download locations in the payload,
    it is not necessary to set "server" location (it is added automatically)
    to the response when an uploaded package is found.
    """

    if not user.is_admin:
        raise ForbiddenException("Only admins can save dependency packages.")

    data = dict_exclude(payload.dict(), ["name", "platform"])

    await Postgres.execute(
        """
        INSERT INTO dependency_packages (name, platform, data)
        VALUES ($1, $2, $3)
        ON CONFLICT (name, platform) DO UPDATE SET data = $3
        """,
        payload.name,
        payload.platform,
        data,
    )

    return EmptyResponse()


@router.get("/dependency_packages/{package_name}/{platform}")
async def download_dependency_package(
    user: CurrentUser,
    package_name: str = Path(...),
    platform: Platform = Path(...),
) -> Response:
    """Download dependency package.

    Use this endpoint to download dependency package stored on the server.
    """

    res = await Postgres.fetch(
        """
        SELECT name, platform FROM dependency_packages
        WHERE name = $1 AND platform = $2
        """,
        package_name,
        platform,
    )

    if not res:
        raise NotFoundException("Package not found.")

    file_path = get_package_file_path(package_name, platform)
    if not os.path.exists(file_path):
        raise NotFoundException("Package file not found.")

    # TODO: use streaming
    return Response(
        media_type="application/octet-stream",
        status_code=200,
        content=open(file_path, "rb").read(),
    )


@router.put("/dependency_packages/{package_name}/{platform}", status_code=204)
async def upload_dependency_package(
    request: Request,
    user: CurrentUser,
    package_name: str = Path(...),
    platform: Platform = Path(...),
) -> EmptyResponse:
    """Upload a dependency package to the server."""

    if not user.is_admin:
        raise ForbiddenException("Only admins can upload dependency packages.")

    res = await Postgres.fetch(
        """
        SELECT
            data->>'size' as size,
            data->>'checksum' as checksum
        FROM dependency_packages
        WHERE name = $1 AND platform = $2
        """,
        package_name,
        platform,
    )

    if not res:
        raise NotFoundException("Package not found.")

    expected_size = int(res[0]["size"])
    expected_checksum = res[0]["checksum"]

    file_path = get_package_file_path(package_name, platform)
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        logging.info(f"Creating directory {directory}")
        os.makedirs(directory)

    with open(file_path, "wb") as f:
        async for chunk in request.stream():
            f.write(chunk)

    file_size = os.path.getsize(file_path)
    if file_size != expected_size:
        raise AyonException(
            "Uploaded file has different size than expected"
            f"expected: {expected_size}, got: {file_size}"
        )

    checksum = md5sum(file_path)
    if checksum != expected_checksum:
        raise AyonException(
            "Uploaded file has different checksum than expected."
            f"expected: {expected_checksum}, got: {checksum}"
        )

    return EmptyResponse()


@router.delete("/dependency_packages/{package_name}/{platform}", status_code=204)
async def delete_dependency_package(
    user: CurrentUser,
    package_name: str = Path(...),
    platform: Platform = Path(...),
) -> EmptyResponse:
    """Delete a dependency package from the server.
    If there is an uploaded package, it will be deleted as well.
    """

    if not user.is_admin:
        raise ForbiddenException("Only admins can delete dependency packages")

    if os.path.exists(file_path := get_package_file_path(package_name, platform)):
        os.remove(file_path)

    await Postgres.execute(
        """
        DELETE FROM dependency_packages
        WHERE name = $1 AND platform = $2
        """,
        package_name,
        platform,
    )

    return EmptyResponse()

from typing import Literal, Any

from fastapi import APIRouter, Depends, Response, Path

from openpype.api import ResponseFactory
from openpype.lib.postgres import Postgres
from openpype.types import OPModel, Field

from openpype.api.dependencies import dep_current_user
from openpype.entities import UserEntity

router = APIRouter(
    prefix="",
    tags=["Events"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)


Platform = Literal["windows", "linux", "darwin"]


class DependencyPackage(OPModel):
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
        title="Sources",
        description="List of sources from which the package was downloaded",
    )


class DependencyPackageList(OPModel):
    packages: list[DependencyPackage] = Field(default_factory=list)
    production_package: str | None = None


@router.get("", response_model=DependencyPackageList)
async def list_dependency_packages():
    pass


@router.post("", response_class=Response)
async def create_dependency_package(
    payload: DependencyPackage,
    user: UserEntity = Depends(dep_current_user),
):
    """Create (or update) a dependency package record in the database.

    You can set external download locations in the payload,
    it is not necessary to set "server" location (it is added automatically)
    to the response when an uploaded package is found.
    """
    pass


@router.get("{package_name}/{platform}")
async def download_dependency_package(
    user: UserEntity = Depends(dep_current_user),
    package_name: str = Path(...),
    platform: Platform = Path(...),
):
    pass


@router.post("{package_name}/{platform}", response_class=Response)
async def upload_dependency_package(
    user: UserEntity = Depends(dep_current_user),
    package_name: str = Path(...),
    platform: Platform = Path(...),
):
    """Upload a dependency package to the server."""
    pass


@router.get("{package_name}/{platform}", response_class=Response)
async def delete_dependency_package(
    user: UserEntity = Depends(dep_current_user),
    package_name: str = Path(...),
    platform: Platform = Path(...),
):
    """Delete a dependency package from the server.
    If there is an uploaded package, it will be deleted as well.
    """
    pass

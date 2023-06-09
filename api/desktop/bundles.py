from datetime import datetime

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.types import Field, OPModel

from .common import Platform
from .router import router

dependency_packages_meta = {
    "title": "Dependency packages",
    "description": "mapping of platform:dependency_package_filename",
    "example": {
        "windows": "a_windows_package123.zip",
        "linux": "a_linux_package123.zip",
        "darwin": "a_mac_package123.zip",
    },
}


class BaseBundleModel(OPModel):
    pass


class BundleModel(BaseBundleModel):
    """
    Model for GET and POST requests
    """

    name: str = Field(
        ...,
        title="Name",
        description="Name of the bundle",
        example="my_superior_bundle",
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        example=datetime.now(),
    )
    installer_version: str = Field(..., example="1.2.3")
    addons: dict[str, str] = Field(
        default_factory=dict,
        title="Addons",
        example={"ftrack": "1.2.3"},
    )
    dependency_packages: dict[Platform, str] = Field(
        default_factory=dict, **dependency_packages_meta
    )
    is_production: bool = Field(False, example=False)
    is_stable: bool = Field(False, example=False)


class BundlePatchModel(BaseBundleModel):
    dependency_packages: dict[Platform, str] | None = Field(
        None, **dependency_packages_meta
    )
    is_production: bool | None = Field(None, example=False)
    is_stable: bool | None = Field(None, example=False)


class ListBundleModel(OPModel):
    bundles: list[BundleModel] = Field(default_factory=list)
    production_bundle: str | None = Field(None, example="my_superior_bundle")
    staging_bundle: str | None = Field(None, example="my_superior_bundle")


@router.get("/bundles")
async def list_bundles() -> ListBundleModel:
    return ListBundleModel()


@router.post("/bundles", status_code=201)
async def create_bundle(bundle: BundleModel, user: CurrentUser) -> EmptyResponse:
    pass


@router.patch("/bundles/{bundle_name}", status_code=204)
async def patch_bundle(
    bundle_name: str,
    bundle: BundlePatchModel,
    user: CurrentUser,
) -> EmptyResponse:
    pass


@router.delete("/bundles/{bundle_name}", status_code=204)
async def delete_bundle(
    bundle_name: str,
    user: CurrentUser,
) -> EmptyResponse:
    pass

from datetime import datetime

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
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
    installer_version: str | None = Field(None, example="1.2.3")
    addons: dict[str, str] = Field(
        default_factory=dict,
        title="Addons",
        example={"ftrack": "1.2.3"},
    )
    dependency_packages: dict[Platform, str] = Field(
        default_factory=dict, **dependency_packages_meta
    )
    is_production: bool = Field(False, example=False)
    is_staging: bool = Field(False, example=False)


class BundlePatchModel(BaseBundleModel):
    dependency_packages: dict[Platform, str | None] = Field(
        default_factory=dict,
        **dependency_packages_meta,
    )
    is_production: bool | None = Field(None, example=False)
    is_staging: bool | None = Field(None, example=False)


class ListBundleModel(OPModel):
    bundles: list[BundleModel] = Field(default_factory=list)
    production_bundle: str | None = Field(None, example="my_superior_bundle")
    staging_bundle: str | None = Field(None, example="my_superior_bundle")


@router.get("/bundles")
async def list_bundles() -> ListBundleModel:
    result: list[BundleModel] = []
    production_bundle: str | None = None
    staging_bundle: str | None = None

    async for row in Postgres.iterate("SELECT * FROM bundles ORDER by created_at DESC"):
        bundle = BundleModel(**row["data"])
        if row["is_production"]:
            production_bundle = row["name"]
        if row["is_staging"]:
            staging_bundle = row["name"]
        result.append(bundle)

    return ListBundleModel(
        bundles=result,
        production_bundle=production_bundle,
        staging_bundle=staging_bundle,
    )


@router.post("/bundles", status_code=201)
async def create_bundle(bundle: BundleModel, user: CurrentUser) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can create bundles")

    try:
        async with Postgres.acquire() as conn:
            async with conn.transaction():
                if bundle.is_production:
                    await conn.execute("UPDATE bundles SET is_production = FALSE")
                if bundle.is_staging:
                    await conn.execute("UPDATE bundles SET is_staging = FALSE")

                query = """
                    INSERT INTO bundles
                    (name, data, is_production, is_staging, created_at)
                    VALUES ($1, $2, $3, $4, $5)
                """

                await conn.execute(
                    query,
                    bundle.name,
                    bundle.dict(),
                    bundle.is_production,
                    bundle.is_staging,
                    bundle.created_at,
                )
    except Postgres.UniqueViolationError:
        raise ConflictException("Bundle with this name already exists")

    return EmptyResponse(status_code=201)


@router.patch("/bundles/{bundle_name}", status_code=204)
async def patch_bundle(
    bundle_name: str,
    bundle: BundlePatchModel,
    user: CurrentUser,
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can patch bundles")

    async with Postgres.acquire() as conn:
        async with conn.transaction():
            res = await conn.fetch(
                "SELECT * FROM bundles WHERE name = $1 FOR UPDATE", bundle_name
            )
            if not res:
                raise NotFoundException("Bundle not found")

            orig_bundle = BundleModel(**res[0]["data"])
            dep_packages = orig_bundle.dependency_packages.copy()
            for key, value in bundle.dependency_packages.items():
                if bundle.dependency_packages is None:
                    dep_packages.pop(key, None)
                elif value is not None:
                    dep_packages[key] = value

            orig_bundle.dependency_packages = dep_packages

            if bundle.is_production is not None:
                orig_bundle.is_production = bundle.is_production
                if orig_bundle.is_production:
                    await conn.execute("UPDATE bundles SET is_production = FALSE")
            if bundle.is_staging is not None:
                orig_bundle.is_staging = bundle.is_staging
                if orig_bundle.is_staging:
                    await conn.execute("UPDATE bundles SET is_staging = FALSE")

            await conn.execute(
                "UPDATE bundles SET data = $1, is_production = $2, is_staging = $3 WHERE name = $4",
                orig_bundle.dict(),
                orig_bundle.is_production,
                orig_bundle.is_staging,
                bundle_name,
            )
    return EmptyResponse(status_code=204)


@router.delete("/bundles/{bundle_name}", status_code=204)
async def delete_bundle(
    bundle_name: str,
    user: CurrentUser,
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can delete bundles")

    await Postgres.execute("DELETE FROM bundles WHERE name = $1", bundle_name)
    return EmptyResponse(status_code=204)

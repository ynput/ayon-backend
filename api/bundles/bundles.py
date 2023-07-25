from datetime import datetime
from typing import Literal

from fastapi import Header, Query

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import UserEntity
from ayon_server.events import dispatch_event
from ayon_server.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import NAME_REGEX, Field, OPModel, Platform

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
        regex=NAME_REGEX,
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        example=datetime.now(),
    )
    installer_version: str | None = Field(None, example="1.2.3")
    addons: dict[str, str | None] = Field(
        default_factory=dict,
        title="Addons",
        example={"ftrack": "1.2.3"},
    )
    dependency_packages: dict[Platform, str | None] = Field(
        default_factory=dict, **dependency_packages_meta
    )
    is_production: bool = Field(False, example=False)
    is_staging: bool = Field(False, example=False)
    is_archived: bool = Field(False, example=False)


class BundlePatchModel(BaseBundleModel):
    dependency_packages: dict[Platform, str | None] = Field(
        default_factory=dict,
        **dependency_packages_meta,
    )
    is_production: bool | None = Field(None, example=False)
    is_staging: bool | None = Field(None, example=False)
    is_archived: bool | None = Field(None, example=False)


class ListBundleModel(OPModel):
    bundles: list[BundleModel] = Field(default_factory=list)
    production_bundle: str | None = Field(None, example="my_superior_bundle")
    staging_bundle: str | None = Field(None, example="my_superior_bundle")


@router.get("/bundles", response_model_exclude_none=True)
async def list_bundles(
    archived: bool = Query(False, description="Include archived bundles"),
) -> ListBundleModel:
    result: list[BundleModel] = []
    production_bundle: str | None = None
    staging_bundle: str | None = None

    async for row in Postgres.iterate("SELECT * FROM bundles ORDER by created_at DESC"):
        bundle = BundleModel(
            **row["data"],
            name=row["name"],
            created_at=row["created_at"],
            is_production=row["is_production"],
            is_staging=row["is_staging"],
            is_archived=row["is_archived"],
        )
        if row["is_production"]:
            production_bundle = row["name"]
        if row["is_staging"]:
            staging_bundle = row["name"]

        if not archived and bundle.is_archived:
            continue

        result.append(bundle)

    return ListBundleModel(
        bundles=result,
        production_bundle=production_bundle,
        staging_bundle=staging_bundle,
    )


async def create_bundle(
    bundle: BundleModel,
    user: UserEntity | None = None,
    sender: str | None = None,
):
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

                data = {**bundle.dict(exclude_none=True)}
                data.pop("name", None)
                data.pop("created_at", None)
                data.pop("is_production", None)
                data.pop("is_staging", None)
                data.pop("is_archived", None)

                # we ignore is_archived. it does not make sense to create
                # an archived bundle

                await conn.execute(
                    query,
                    bundle.name,
                    data,
                    bundle.is_production,
                    bundle.is_staging,
                    bundle.created_at,
                )
    except Postgres.UniqueViolationError:
        raise ConflictException("Bundle with this name already exists")

    await dispatch_event(
        "bundle.created",
        sender=sender,
        user=user.name if user else None,
        description=f"Bundle {bundle.name} created",
        summary={
            "name": bundle.name,
            "isProduction": bundle.is_production,
            "isStaging": bundle.is_staging,
        },
        payload=data,
    )


@router.post("/bundles", status_code=201)
async def create_new_bundle(
    bundle: BundleModel,
    user: CurrentUser,
    validate: bool = Query(False, description="Ensure specified addons exist"),
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can create bundles")

    if validate:
        for addon_name, addon_version in bundle.addons.items():
            # Raise exception if addon if you are trying to add
            # a bundle with an addon that does not exist
            if not addon_version:
                continue
            _ = AddonLibrary.addon(addon_name, addon_version)

    await create_bundle(bundle, user, x_sender)

    return EmptyResponse(status_code=201)


@router.patch("/bundles/{bundle_name}", status_code=204)
async def patch_bundle(
    bundle_name: str,
    bundle: BundlePatchModel,
    user: CurrentUser,
    build: list[Platform]
    | None = Query(
        None,
        title="Request build",
        description="Build dependency packages for selected platforms",
    ),
    x_sender: str | None = Header(default=None),
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
            row = res[0]

            orig_bundle = BundleModel(
                **row["data"],
                name=row["name"],
                created_at=row["created_at"],
                is_production=row["is_production"],
                is_staging=row["is_staging"],
                is_archived=row["is_archived"],
            )
            dep_packages = orig_bundle.dependency_packages.copy()
            for key, value in bundle.dependency_packages.items():
                if bundle.dependency_packages is None:
                    dep_packages.pop(key, None)
                elif type(value) is str:
                    dep_packages[key] = value

            orig_bundle.dependency_packages = dep_packages

            if bundle.is_archived:
                if (
                    orig_bundle.is_production
                    or orig_bundle.is_staging
                    or bundle.is_production
                    or bundle.is_staging
                ):
                    raise BadRequestException(
                        "Cannot archive bundle that is production or staging"
                    )

                bundle.is_production = False
                bundle.is_staging = False
                orig_bundle.is_archived = True
            elif bundle.is_archived is False:
                orig_bundle.is_archived = False

            if bundle.is_production is not None:
                orig_bundle.is_production = bundle.is_production
                if orig_bundle.is_production:
                    await conn.execute("UPDATE bundles SET is_production = FALSE")
            if bundle.is_staging is not None:
                orig_bundle.is_staging = bundle.is_staging
                if orig_bundle.is_staging:
                    await conn.execute("UPDATE bundles SET is_staging = FALSE")

            data = {**orig_bundle.dict(exclude_none=True)}
            data.pop("name", None)
            data.pop("created_at", None)
            data.pop("is_production", None)
            data.pop("is_staging", None)
            data.pop("is_archived", None)

            await conn.execute(
                """
                UPDATE bundles
                SET data = $1, is_production = $2, is_staging = $3, is_archived = $4
                WHERE name = $5
                """,
                data,
                orig_bundle.is_production,
                orig_bundle.is_staging,
                orig_bundle.is_archived,
                bundle_name,
            )

    await dispatch_event(
        "bundle.updated",
        sender=x_sender,
        user=user.name,
        description=f"Bundle {bundle_name} updated",
        summary={
            "name": bundle_name,
            "isProduction": bundle.is_production,
            "isStaging": bundle.is_staging,
            "isArchived": bundle.is_archived,
        },
        payload=data,
    )

    if build:
        # TODO
        pass

    return EmptyResponse(status_code=204)


async def delete_bundle(bundle_name: str):
    await Postgres.execute("DELETE FROM bundles WHERE name = $1", bundle_name)


@router.delete("/bundles/{bundle_name}", status_code=204)
async def delete_existing_bundle(
    bundle_name: str,
    user: CurrentUser,
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can delete bundles")
    await delete_bundle(bundle_name)
    return EmptyResponse(status_code=204)


class BundleActionModel(OPModel):
    action: Literal["promote"] = Field(..., example="promote")


async def promote_bundle(bundle: BundleModel, user: UserEntity, conn):
    """Promote a bundle to production.

    That includes copying staging settings to production.
    """

    if not user.is_admin:
        raise ForbiddenException("Only admins can promote bundles")

    if not bundle.is_staging:
        raise BadRequestException("Only staging bundles can be promoted")

    await conn.execute("UPDATE bundles SET is_production = FALSE")
    await conn.execute(
        """
        UPDATE bundles
        SET is_production = TRUE
        WHERE name = $1
        """,
        bundle.name,
    )

    # Get project list
    # statement = await conn.prepare("SELECT name FROM projects")
    # project_names = [row["name"] async for row in statement.cursor()]

    # Copy staging settings to production

    for addon_name, addon_version in bundle.addons.items():
        sres = await conn.fetch(
            """
                SELECT data FROM settings
                WHERE addon_name = $1 AND addon_version = $2
                AND variant = 'staging'
                """,
            addon_name,
            addon_version,
        )
        if not sres:
            data = {}
        else:
            data = sres[0]["data"]
        await conn.execute(
            """
            INSERT INTO settings (addon_name, addon_version, variant, data)
            VALUES ($1, $2, 'production', $3)
            ON CONFLICT (addon_name, addon_version, variant)
            DO UPDATE SET data = $3
            """,
            addon_name,
            addon_version,
            data,
        )

        # Do the same for every active project settings
        # TODO: Do we want this?
        #
        # for project_name in project_names:


@router.post("/bundles/{bundle_name}", status_code=201)
async def bundle_actions(
    bundle_name: str,
    action: BundleActionModel,
    user: CurrentUser,
) -> EmptyResponse:
    """Perform actions on bundles."""

    async with Postgres.acquire() as conn:
        async with conn.transaction():
            res = await conn.fetch(
                "SELECT * FROM bundles WHERE name = $1 FOR UPDATE", bundle_name
            )
            if not res:
                raise NotFoundException("Bundle not found")
            row = res[0]
            bundle = BundleModel(
                **row["data"],
                name=row["name"],
                created_at=row["created_at"],
                is_production=row["is_production"],
                is_staging=row["is_staging"],
                is_archived=row["is_archived"],
            )

            if bundle.is_archived:
                raise BadRequestException("Archived bundles cannot be modified")

            if action.action == "promote":
                return await promote_bundle(bundle, user, conn)

    return EmptyResponse(status_code=204)

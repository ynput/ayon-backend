from fastapi import APIRouter

from openpype.addons import AddonLibrary

# from openpype.api import ResponseFactory
from openpype.lib.postgres import Postgres
from openpype.types import Field, OPModel

#
# Router
#

router = APIRouter(
    prefix="/addons",
    tags=["addons"],
)

#
# [POST] /usd/resolve
#


class AddonListItem(OPModel):
    name: str = Field(
        ...,
        description="Name of the addon",
    )
    versions: list[str] = Field(
        ...,
        description="List of available versions of the addon",
    )
    description: str = Field(
        ...,
        description="Description of the addon",
    )
    production_version: str | None = Field(
        None,
        description="Production version of the addon",
    )
    staging_version: str | None = Field(
        None,
        description="Staging version of the addon",
    )


class AddonList(OPModel):
    addons: list[AddonListItem] = Field(
        ...,
        description="List of available addons",
    )


@router.get("", response_model=AddonList)
async def list_addons():

    result = []
    library = AddonLibrary.getinstance()

    #maybe some ttl here?
    active_versions = await library.get_active_versions()

    for name, addon in library.data.items():
        vers = active_versions.get(addon.name, {})
        result.append(
            AddonListItem(
                name=addon.name,
                versions=list(addon.versions.keys()),
                description=addon.description,
                production_version=vers.get("production"),
                staging_version=vers.get("staging"),
            )
        )
    return AddonList(addons=result)


#
# Addons configuration
#


class AddonVersionConfig(OPModel):
    productionVersion: str | None = Field(None)
    stagingVersion: str | None = Field(None)


class AddonConfigRequest(OPModel):
    versions: dict[str, AddonVersionConfig] | None = Field(None)


@router.post("")
async def configure_addons(payload: AddonConfigRequest):
    if payload.versions:
        for name, version_config in payload.versions.items():
            await Postgres.execute(
                """
                INSERT INTO addon_versions
                (name, production_version, staging_version) VALUES ($1, $2, $3)
                ON CONFLICT (name)
                DO UPDATE SET  production_version = $2, staging_version = $3
            """,
                name,
                version_config.productionVersion,
                version_config.stagingVersion,
            )


#
# Addon settings
#


@router.get("/{addon}/system_settings")
async def get_addon_system_settings(addon: str):
    return {}


@router.get("/{addon_name}/system_settings/schema")
async def get_addon_system_settings_schema(addon_name: str):
    library = AddonLibrary.getinstance()

    if (addon := library.get(addon_name)) is None:
        return {}

    return addon.versions["1.0.0"].system_settings.schema()

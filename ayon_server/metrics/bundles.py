from ayon_server.addons.library import AddonLibrary
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel


class ProductionBundle(OPModel):
    addons: dict[str, str] = Field(
        default_factory=dict,
        title="Addons",
        example={
            "maya": "1.0.0",
            "nuke": "1.0.0",
            "ftrack": "1.0.0",
        },
    )
    launcher_version: str | None = Field(
        None,
        title="Launcher version",
        example="1.0.0",
    )


async def get_production_bundle(saturated: bool) -> ProductionBundle | None:
    """Addons and their versions used in the production bundle

    We track what addons are used in the production bundle, as well as what
    launcher version is used. This is used to determine if the production
    bundle is up to date with the latest addons and launcher version,
    and if not, to notify the user that they should update in case of
    security issues or other important changes.
    """

    query = "SELECT data FROM bundles WHERE is_production IS TRUE"
    res = await Postgres.fetch(query)
    if not res:
        return None

    bundle_data = res[0]["data"]

    return ProductionBundle(
        addons=bundle_data.get("addons", {}),
        launcher_version=bundle_data.get("installer_version", ""),
    )


async def get_installed_addons(saturated: bool) -> list[tuple[str, str]]:
    """Addons and their versions installed on the server

    We track what addons are installed on the server, and compare this to the
    addons which are actually used in the production bundle.
    """

    result = []
    for addon_name, definition in AddonLibrary.items():
        for version in definition.versions.keys():
            result.append((addon_name, version))
    return result

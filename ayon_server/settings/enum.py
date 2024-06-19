from aiocache import cached

from ayon_server.lib.postgres import Postgres
from ayon_server.settings.anatomy import Anatomy


async def get_primary_anatomy_preset():
    query = "SELECT * FROM anatomy_presets WHERE is_primary is TRUE"
    async for row in Postgres.iterate(query):
        return Anatomy(**row["data"])
    return Anatomy()


async def folder_types_enum(project_name: str | None = None):
    if project_name is None:
        anatomy = await get_primary_anatomy_preset()
        return [folder_type.name for folder_type in anatomy.folder_types]

    return [
        row["name"]
        async for row in Postgres.iterate(
            f"""
            SELECT name
            FROM project_{project_name}.folder_types
            ORDER BY POSITION
            """
        )
    ]


async def task_types_enum(project_name: str | None = None):
    if project_name is None:
        anatomy = await get_primary_anatomy_preset()
        return [task_type.name for task_type in anatomy.task_types]

    return [
        row["name"]
        async for row in Postgres.iterate(
            f"""
            SELECT name
            FROM project_{project_name}.task_types
            ORDER BY POSITION
            """
        )
    ]


async def secrets_enum(project_name: str | None = None) -> list[str]:
    """Return a list of all sercrets (only names)."""
    return [
        row["name"]
        async for row in Postgres.iterate("SELECT name FROM secrets ORDER BY name")
    ]


async def anatomy_presets_enum():
    query = "SELECT name, is_primary FROM anatomy_presets ORDER BY name"
    primary: str | None = None
    result = []
    async for row in Postgres.iterate(query):
        if row["is_primary"]:
            label = f"{row['name']} (primary)"
            primary = row["name"]
        else:
            label = row["name"]
        result.append({"label": label, "value": row["name"]})

    if primary is not None:
        primary_label = f"<PRIMARY ({primary})>"
    else:
        primary_label = "<PRIMARY (built-in)>"
    result.insert(0, {"value": "__primary__", "label": primary_label})
    result.insert(1, {"value": "__builtin__", "label": "<BUILT-IN>"})
    return result


#
# Addon host names
#


async def _get_app_host_names():
    from ayon_server.addons.library import AddonLibrary

    # TODO: instead of set, use dict and along with the
    # host name, store the variant which uses it
    # to allow future expansion to addon_production_app_host_names_enum
    # and addon_staging_app_host_names_enum

    result = set()
    for _, definition in AddonLibrary.items():
        for version in definition.versions.values():
            for host_name in await version.get_app_host_names():
                result.add(host_name)
    return sorted(result)


@cached(ttl=3600)
async def addon_all_app_host_names_enum():
    result = await _get_app_host_names()
    return [{"label": host_name, "value": host_name} for host_name in result]


async def application_enum(apps=None) -> list[dict]:
    """Return a list of all applications.

    If app is provided, return only applications that start with app.

    Example:
        nuke_variant: str = SettingsField(
            default="",
            title="Nuke variant",
            description="Nuke variant to be used for transcoding.",
            enum_resolver=functools.partial(application_enum, "nuke"),
        )

    Args:
        app Optional[list[str]]: Application names to filter. Defaults to None.

    Returns:
        list[dict]: List of applications.
    """
    res = await Postgres.fetch(
        "SELECT data FROM attributes WHERE name = 'applications'"
    )
    if not res:
        return []
    all_apps = res[0]["data"].get("enum", [])

    if apps:
        return_apps = []
        for app in apps:
            return_apps += [
                a for a in all_apps if a["value"].split("/")[0] == app.lower()
            ]
        return return_apps

    return all_apps


async def tools_enum() -> list[str]:
    """Return a list of all tools."""
    res = await Postgres.fetch(
        "SELECT data FROM attributes WHERE name = 'tools'")

    return res[0]["data"].get("enum", []) if res else []

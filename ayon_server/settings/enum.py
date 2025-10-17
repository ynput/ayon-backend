"""Various enums for settings and elsewhere.

Individual resolvers from this module will be moved to ayon_server.enum in future,
so they will be available in /api/enum/ endpoint as well.
"""

import functools
from collections.abc import Coroutine
from typing import Any, Literal

from aiocache import cached

from ayon_server.entities.core.attrib import attribute_library
from ayon_server.enum import EnumItem
from ayon_server.lib.postgres import Postgres
from ayon_server.settings.anatomy import Anatomy


async def attributes_enum() -> list[EnumItem]:
    got = set()
    result = []
    for attributes in attribute_library.data.values():
        for attribute in attributes:
            if attribute["name"] in got:
                continue
            got.add(attribute["name"])
            result.append(
                EnumItem(
                    value=attribute["name"],
                    label=attribute.get("title", attribute["name"]),
                )
            )
    result.sort(key=lambda x: x.label)
    return result


async def get_primary_anatomy_preset() -> Anatomy:
    query = "SELECT * FROM anatomy_presets WHERE is_primary is TRUE"
    async for row in Postgres.iterate(query):
        return Anatomy(**row["data"])
    return Anatomy()


async def addons_enum() -> list[EnumItem]:
    """Return a list of all installed addons"""
    from ayon_server.addons.library import AddonLibrary

    instance = AddonLibrary.getinstance()
    result = []
    for addon_name, definition in instance.items():
        result.append(
            EnumItem(
                value=addon_name,
                label=definition.friendly_name,
            )
        )
    result.sort(key=lambda x: x.label)
    return result


async def folder_types_enum(project_name: str | None = None) -> list[str]:
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


async def product_types_enum() -> list[str]:
    return [
        row["name"]
        async for row in Postgres.iterate(
            """
            SELECT name FROM public.product_types
            ORDER BY name
            """
        )
    ]


async def task_types_enum(project_name: str | None = None) -> list[str]:
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


async def link_types_enum(project_name: str | None = None) -> list[EnumItem]:
    result = []
    if project_name is None:
        anatomy = await get_primary_anatomy_preset()
        for link_type in anatomy.link_types:
            lt = link_type.link_type
            li = link_type.input_type
            lo = link_type.output_type

            label = f"{lt.capitalize()} ({li.capitalize()} -> {lo.capitalize()})"
            value = f"{lt}|{li}|{lo}"
            result.append(
                EnumItem(
                    label=label,
                    value=value,
                    color=link_type.color,
                )
            )

        return result

    q = f"SELECT * FROM project_{project_name}.link_types ORDER BY name"
    async for row in Postgres.iterate(q):
        lt = row["link_type"]
        li = row["input_type"]
        lo = row["output_type"]
        label = f"{lt.capitalize()} ({li.capitalize()} -> {lo.capitalize()})"
        value = f"{lt}|{li}|{lo}"
        result.append(
            EnumItem(
                label=label,
                value=value,
                color=row["data"].get("color", None),
            )
        )
    return result


async def secrets_enum(project_name: str | None = None) -> list[str]:
    """Return a list of all sercrets (only names)."""
    return [
        row["name"]
        async for row in Postgres.iterate("SELECT name FROM secrets ORDER BY name")
    ]


async def anatomy_presets_enum() -> list[EnumItem]:
    query = "SELECT name, is_primary FROM anatomy_presets ORDER BY name"
    primary: str | None = None
    result = []
    async for row in Postgres.iterate(query):
        if row["is_primary"]:
            label = f"{row['name']} (primary)"
            primary = row["name"]
        else:
            label = row["name"]
        result.append(EnumItem(label=label, value=row["name"]))

    if primary is not None:
        primary_label = f"<PRIMARY ({primary})>"
    else:
        primary_label = "<PRIMARY (built-in)>"
    result.insert(0, EnumItem(value="__primary__", label=primary_label))
    result.insert(1, EnumItem(value="__builtin__", label="<BUILT-IN>"))
    return result


#
# Anatomy template items
#

TemplateItemsCategory = Literal[
    "work", "publish", "hero", "delivery", "others", "staging"
]


def anatomy_template_items_enum(
    category: TemplateItemsCategory,
) -> functools.partial[Coroutine[Any, Any, list[EnumItem]]]:
    """Provides values of template names from Anatomy as dropdown.

    Wrapper for actual function as Settings require callable.

    Args:
        category: str: type of templates 'publish'|'render'...

    Returns:
        list[dict[str,str]]

    """
    return functools.partial(
        _anatomy_template_items_enum, project_name=None, category=category
    )


async def _anatomy_template_items_enum(
    project_name: str | None,
    category: TemplateItemsCategory,
) -> list[EnumItem]:
    if not project_name:
        template_names = await _get_template_names_studio(category)
    else:
        template_names = await _get_template_names_project(project_name, category)

    return [
        EnumItem(label=template_name, value=template_name)
        for template_name in sorted(template_names)
    ]


async def _get_template_names_project(
    project_name: str,
    category: TemplateItemsCategory,
) -> list[str]:
    template_names = []

    query = (
        f"SELECT config->'templates' as tpls "
        f"FROM public.projects WHERE name = '{project_name}'"
    )
    async for row in Postgres.iterate(query):
        templates = row["tpls"]
        template_category = templates.get(category, {})
        template_names.extend(template_category.keys())
    return template_names


async def _get_template_names_studio(category: TemplateItemsCategory) -> list[str]:
    anatomy = await get_primary_anatomy_preset()
    data = anatomy.dict()

    return [template["name"] for template in data["templates"].get(category, {})]


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
async def addon_all_app_host_names_enum() -> list[EnumItem]:
    result = await _get_app_host_names()
    return [EnumItem(label=host_name, value=host_name) for host_name in result]

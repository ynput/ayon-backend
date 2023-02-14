from typing import Literal

from nxtools import log_traceback

from ayon_server.addons import AddonLibrary
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.settings import BaseSettingsModel
from ayon_server.types import Field, OPModel
from ayon_server.utils import dict_remove_path


class ModifyOverridesRequestModel(OPModel):
    action: Literal["delete", "pin"] = Field(..., title="Action")
    path: list[str] = Field(..., title="Path")


async def remove_override(
    addon_name: str,
    addon_version: str,
    path: list[str],
    variant: str = "production",
    project_name: str | None = None,
):
    if (addon := AddonLibrary.addon(addon_name, addon_version)) is None:
        raise NotFoundException(f"Addon {addon_name} {addon_version} not found")

    # TODO: ensure the path is not a part of a group

    if project_name:
        scope = f"project_{project_name}."
        overrides = await addon.get_project_overrides(project_name, variant=variant)
    else:
        scope = "public."
        overrides = await addon.get_studio_overrides(variant=variant)

    try:
        dict_remove_path(overrides, path)
    except KeyError:
        log_traceback()
        return

    await Postgres.execute(
        f"""
        INSERT INTO {scope}settings
            (addon_name, addon_version, variant, data)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (addon_name, addon_version, variant)
        DO UPDATE SET data = $4
        """,
        addon_name,
        addon_version,
        variant,
        overrides,
    )


async def pin_override(
    addon_name: str,
    addon_version: str,
    path: list[str],
    variant: str = "production",
    project_name: str | None = None,
):
    if (addon := AddonLibrary.addon(addon_name, addon_version)) is None:
        raise NotFoundException(f"Addon {addon_name} {addon_version} not found")

    if project_name:
        scope = f"project_{project_name}."
        overrides = await addon.get_project_overrides(project_name, variant=variant)
        settings = await addon.get_project_settings(project_name, variant=variant)
    else:
        scope = ""
        overrides = await addon.get_studio_overrides(variant=variant)
        settings = await addon.get_studio_settings(variant=variant)

    c_field = settings
    c_overr = overrides

    for i, key in enumerate(path):
        if key not in c_field.__fields__:
            raise KeyError(f"{key} is not present in {c_field}")

        c_field = getattr(c_field, key)
        is_group = False
        if isinstance(c_field, BaseSettingsModel):
            is_group = c_field._isGroup
        else:
            is_group = True

        if not is_group:
            if key not in c_overr:
                c_overr[key] = {}
            c_overr = c_overr[key]
            continue

        if isinstance(c_field, BaseSettingsModel):
            c_overr[key] = c_field.dict()
        elif isinstance(c_field, list):
            val = []
            for r in c_field:
                if isinstance(r, BaseSettingsModel):
                    val.append(r.dict())
                else:
                    val.append(r)
            c_overr[key] = val
        else:
            c_overr[key] = c_field
        break

    await Postgres.execute(
        f"""
        INSERT INTO {scope}settings
            (addon_name, addon_version, variant, data)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (addon_name, addon_version, variant)
        DO UPDATE SET data = $4
        """,
        addon_name,
        addon_version,
        variant,
        overrides,
    )

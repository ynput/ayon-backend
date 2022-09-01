from typing import Literal

from nxtools import log_traceback

from openpype.addons import AddonLibrary
from openpype.exceptions import NotFoundException
from openpype.lib.postgres import Postgres
from openpype.settings import BaseSettingsModel
from openpype.types import Field, OPModel
from openpype.utils import dict_remove_path, json_loads


class ModifyOverridesRequestModel(OPModel):
    action: Literal["delete", "pin"] = Field(..., title="Action")
    path: list[str] = Field(..., title="Path")


async def remove_override(
    addon_name: str,
    addon_version: str,
    path: list[str],
    project_name: str | None = None,
):
    if (addon := AddonLibrary.addon(addon_name, addon_version)) is None:
        raise NotFoundException(f"Addon {addon_name} {addon_version} not found")

    # TODO: ensure the path is not a part of a group

    if project_name:
        scope = f"project_{project_name}."
        overrides = await addon.get_project_overrides(project_name)
    else:
        scope = ""
        overrides = await addon.get_studio_overrides()

    try:
        dict_remove_path(overrides, path)
    except KeyError:
        log_traceback()
        return

    # Do not use versioning during the development (causes headaches)

    await Postgres.execute(
        f"DELETE FROM {scope}settings WHERE addon_name = $1 AND addon_version = $2",
        addon_name,
        addon_version,
    )

    await Postgres.execute(
        f"""
        INSERT INTO {scope}settings (addon_name, addon_version, data)
        VALUES ($1, $2, $3)
        """,
        addon_name,
        addon_version,
        overrides,
    )


async def pin_override(
    addon_name: str,
    addon_version: str,
    path: list[str],
    project_name: str | None = None,
):
    if (addon := AddonLibrary.addon(addon_name, addon_version)) is None:
        raise NotFoundException(f"Addon {addon_name} {addon_version} not found")

    if project_name:
        scope = f"project_{project_name}."
        overrides = await addon.get_project_overrides(project_name)
        settings = await addon.get_project_settings(project_name)
    else:
        scope = ""
        overrides = await addon.get_studio_overrides()
        settings = await addon.get_studio_settings()

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

    # Do not use versioning during the development (causes headaches)

    await Postgres.execute(
        f"DELETE FROM {scope}settings WHERE addon_name = $1 AND addon_version = $2",
        addon_name,
        addon_version,
    )

    await Postgres.execute(
        f"""
        INSERT INTO {scope}settings (addon_name, addon_version, data)
        VALUES ($1, $2, $3)
        """,
        addon_name,
        addon_version,
        overrides,
    )

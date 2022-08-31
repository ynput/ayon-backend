from typing import Literal

from nxtools import log_traceback

from openpype.addons import AddonLibrary
from openpype.exceptions import NotFoundException
from openpype.lib.postgres import Postgres
from openpype.types import Field, OPModel
from openpype.utils import dict_remove_path


class ModifyOverridesRequestModel(OPModel):
    action: Literal["delete"] = Field(..., title="Action")
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

    model = addon.get_settings_model()

    # TODO: ensure the path is not a part of a group

    if project_name:
        scope = f"project_{project_name}."
        overrides = await addon.get_project_overrides(project_name)
        settings = await addon.get_project_settings(project_name)
    else:
        scope = ""
        overrides = await addon.get_studio_overrides()
        settings = await addon.get_studio_settings()

    assert scope
    assert overrides
    assert model
    assert settings

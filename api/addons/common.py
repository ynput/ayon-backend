from typing import Any, Literal

from ayon_server.addons import AddonLibrary
from ayon_server.exceptions import NotFoundException
from ayon_server.settings import BaseSettingsModel
from ayon_server.settings.set_addon_settings import set_addon_settings
from ayon_server.types import Field, OPModel
from ayon_server.utils import dict_remove_path


class ModifyOverridesRequestModel(OPModel):
    action: Literal["delete", "pin"] = Field(..., title="Action")
    path: list[str] = Field(..., title="Path")


def _pin_model(model: BaseSettingsModel, target: dict[str, Any]) -> None:
    """Pin all fields of a non-group model to the target overrides.

    Non-group submodels are crawled recursively, everything else
    (groups, lists, scalars) is pinned as a whole.
    """
    data = model.model_dump()
    for key in type(model).model_fields:
        value = getattr(model, key)
        if isinstance(value, BaseSettingsModel) and not value._isGroup:
            if not isinstance(target.get(key), dict):
                target[key] = {}
            _pin_model(value, target[key])
        else:
            target[key] = data[key]


def _pin_path(
    settings: BaseSettingsModel,
    overrides: dict[str, Any],
    path: list[str],
) -> None:
    """Pin the current value of the field at the given path to overrides."""
    c_field: Any = settings
    c_overr = overrides

    for key in path:
        if not isinstance(c_field, BaseSettingsModel) or (
            key not in type(c_field).model_fields
        ):
            raise KeyError(f"{key} is not present in {c_field}")

        parent = c_field
        c_field = getattr(c_field, key)
        if isinstance(c_field, BaseSettingsModel) and not c_field._isGroup:
            if not isinstance(c_overr.get(key), dict):
                c_overr[key] = {}
            c_overr = c_overr[key]
            continue

        # Groups, lists and scalars are pinned as a whole
        c_overr[key] = parent.model_dump()[key]
        return

    # Path points to a non-group model: pin all its children
    _pin_model(c_field, c_overr)


async def remove_override(
    addon_name: str,
    addon_version: str,
    path: list[str],
    variant: str = "production",
    project_name: str | None = None,
    user_name: str | None = None,
):
    if (addon := AddonLibrary.addon(addon_name, addon_version)) is None:
        raise NotFoundException(f"Addon {addon_name} {addon_version} not found")

    # TODO: ensure the path is not a part of a group

    if project_name:
        overrides = await addon.get_project_overrides(project_name, variant=variant)
    else:
        overrides = await addon.get_studio_overrides(variant=variant)

    dict_remove_path(overrides, path)

    await set_addon_settings(
        addon_name,
        addon_version,
        overrides,
        variant=variant,
        project_name=project_name,
        user_name=user_name,
    )


async def pin_override(
    addon_name: str,
    addon_version: str,
    path: list[str],
    variant: str = "production",
    project_name: str | None = None,
    user_name: str | None = None,
):
    if (addon := AddonLibrary.addon(addon_name, addon_version)) is None:
        raise NotFoundException(f"Addon {addon_name} {addon_version} not found")

    if project_name:
        overrides = await addon.get_project_overrides(project_name, variant=variant)
        settings = await addon.get_project_settings(project_name, variant=variant)
    else:
        overrides = await addon.get_studio_overrides(variant=variant)
        settings = await addon.get_studio_settings(variant=variant)

    if not settings:
        return

    _pin_path(settings, overrides, path)

    await set_addon_settings(
        addon_name,
        addon_version,
        overrides,
        variant=variant,
        project_name=project_name,
        user_name=user_name,
    )


# Site overrides
# They are slightly different so we rather duplicate some code than
# make it more complex


async def remove_site_override(
    addon_name: str,
    addon_version: str,
    project_name: str,
    site_id: str,
    user_name: str,
    path: list[str],
):
    if (addon := AddonLibrary.addon(addon_name, addon_version)) is None:
        raise NotFoundException(f"Addon {addon_name} {addon_version} not found")

    overrides = await addon.get_project_site_overrides(project_name, user_name, site_id)

    dict_remove_path(overrides, path)

    await set_addon_settings(
        addon_name,
        addon_version,
        overrides,
        project_name=project_name,
        site_id=site_id,
        user_name=user_name,
    )


async def pin_site_override(
    addon_name: str,
    addon_version: str,
    project_name: str,
    site_id: str,
    user_name: str,
    path: list[str],
):
    if (addon := AddonLibrary.addon(addon_name, addon_version)) is None:
        raise NotFoundException(f"Addon {addon_name} {addon_version} not found")

    overrides = await addon.get_project_site_overrides(project_name, user_name, site_id)
    settings = await addon.get_project_site_settings(project_name, user_name, site_id)

    if not settings:
        return

    _pin_path(settings, overrides, path)

    await set_addon_settings(
        addon_name,
        addon_version,
        overrides,
        project_name=project_name,
        site_id=site_id,
        user_name=user_name,
    )

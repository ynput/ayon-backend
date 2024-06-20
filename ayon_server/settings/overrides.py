from typing import Any

from nxtools import logging

from ayon_server.settings.common import BaseSettingsModel


def apply_overrides(
    settings: BaseSettingsModel,
    overrides: dict[str, Any],
) -> BaseSettingsModel:
    """Take a system settings object and apply the overrides to it.

    Overrides are a dictionary of the same structure as the settings object,
    but only the values that have been overridden are included (which is
    the way overrides are stored in the database).
    """
    result: dict[str, Any] = {}

    def crawl(
        obj: BaseSettingsModel,
        override: dict[str, Any],
        target: dict[str, Any],
    ) -> None:
        for name, _field in obj.__fields__.items():
            child = getattr(obj, name)
            if isinstance(child, BaseSettingsModel):
                target[name] = {}
                crawl(child, override.get(name, {}), target[name])
            else:
                # Naive types
                if name in override:
                    try:
                        # TODO: WTF??
                        type(child)(override[name])
                    except ValueError:
                        logging.warning(f"Invalid value for {name}: {override[name]}")
                        continue
                    except TypeError:
                        # This is okay
                        pass

                    target[name] = override[name]
                else:
                    target[name] = child

    crawl(settings, overrides, result)
    return settings.__class__(**result)


def list_overrides(
    obj: BaseSettingsModel,
    override: dict[str, Any],
    crumbs: list[str] | None = None,
    level: str = "studio",
    in_group: list[str] | None = None,
) -> dict[str, Any]:
    """Returns values which are overriden.

    This is used in the settings form context.
    Return a dictionary of the form:
        {
            key : {            // idSchema of the field as used in rjsf
                "path": path,  // list of parent keys and the current key
                "type": type,  // type of the field: branch, leaf, group, array
                "value": value, // value of the field (only present on leaves)
                "level": level, // source of the override: studio, project or site
                "inGroup": path // path of the group the field is in
            }
        }

    """

    result = {}

    if crumbs is None:
        crumbs = []
        root = "root"
    else:
        root = "root_" + "_".join(crumbs)

    for name, _field in obj.__fields__.items():
        child = getattr(obj, name)
        path = f"{root}_{name}"
        chcrumbs = [*crumbs, name]

        if isinstance(child, BaseSettingsModel):
            if name in override:
                result[path] = {
                    "path": chcrumbs,
                    "type": "group" if child._isGroup else "branch",
                    "level": level,
                    "inGroup": in_group,
                }
            result.update(
                list_overrides(
                    child,
                    override.get(name, {}),
                    chcrumbs,
                    level,
                    in_group=chcrumbs if child._isGroup else in_group,
                )
            )

        elif isinstance(child, list):
            if name in override:
                result[path] = {
                    "path": chcrumbs,
                    "type": "list",
                    "level": level,
                    "inGroup": in_group,
                }

                for i, item in enumerate(child):
                    ovr = override[name][i]
                    if isinstance(item, BaseSettingsModel):
                        result.update(
                            list_overrides(
                                item,
                                ovr,
                                [*chcrumbs, f"{i}"],
                                level=level,
                                in_group=in_group or chcrumbs,
                            )
                        )
                    else:
                        result[f"{path}_{i}"] = {
                            "path": [*chcrumbs, f"{i}"],
                            "level": "default",
                            "value": item,
                            "inGroup": in_group or chcrumbs,
                        }

        elif isinstance(child, tuple):
            if name in override:
                result[path] = {
                    "path": chcrumbs,
                    "value": override[name] if name in override else list(child),
                    "level": level if name in override else "default",
                    "inGroup": in_group,
                }

        elif name in override:
            result[path] = {
                "path": chcrumbs,
                "value": override[name],
                "level": level,
                "inGroup": in_group,
            }

    return result


def paths_to_dict(paths: list[list[str]]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    for path in paths:
        current = root
        for key in path:
            if key not in current:
                current[key] = {}
            current = current[key]
    return root


def extract_overrides(
    default: BaseSettingsModel,
    overriden: BaseSettingsModel,
    existing: dict[str, Any] | None = None,
    explicit_pins: list[list[str]] | None = None,
    explicit_unpins: list[list[str]] | None = None,
) -> dict[str, Any]:
    existing_overrides = existing or {}
    explicit_pins = explicit_pins or []
    explicit_unpins = explicit_unpins or []

    result: dict[str, Any] = {}

    def crawl(
        original_object: BaseSettingsModel,
        new_object: BaseSettingsModel,
        existing_overrides: dict[str, Any],
        target: dict[str, Any],
        path: list[str],
    ):
        for field_name in original_object.__fields__.keys():
            old_child = getattr(original_object, field_name)
            new_child = getattr(new_object, field_name)
            field_path = [*path, field_name]

            if isinstance(old_child, BaseSettingsModel) and not old_child._isGroup:
                if field_path in explicit_pins:
                    target[field_name] = new_child.dict()

                elif old_child.dict() != new_child.dict() or (
                    field_name in existing_overrides
                ):
                    target[field_name] = {}
                    crawl(
                        original_object=old_child,
                        new_object=new_child,
                        existing_overrides=existing_overrides.get(field_name, {}),
                        target=target[field_name],
                        path=field_path,
                    )
            else:
                if (
                    old_child != new_child
                    or (field_name in existing_overrides)
                    or (field_path in explicit_pins)
                ):
                    # we need to use the original object to get the default value
                    # because of the array handling
                    # old_value = original_object.dict()[field_name]
                    new_value = new_object.dict()[field_name]
                    target[field_name] = new_value

    crawl(default, overriden, existing_overrides, result, [])

    # remove paths that are explicitly unpinned

    for path in explicit_unpins:
        current = result
        for key in path[:-1]:
            current = current[key]
        current.pop(path[-1], None)

    return result

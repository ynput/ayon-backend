import os
from typing import Annotated

import semver
from fastapi import Query

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.deprecations import get_deprecations, split_addon_path
from ayon_server.exceptions import ForbiddenException
from ayon_server.types import Field, OPModel

from .router import router


class DeprecationItem(OPModel):
    category: Annotated[
        str,
        Field(
            title="Warning category",
            examples=["PydanticDeprecatedSince20"],
        ),
    ]
    message: Annotated[str, Field(title="Warning message")]
    file: Annotated[
        str,
        Field(
            title="File",
            description="Path relative to the addon or server directory",
            examples=["server/settings/main.py"],
        ),
    ]
    line: Annotated[int, Field(title="Line number")]
    count: Annotated[
        int,
        Field(
            title="Count",
            description="How many times the deprecated feature was used",
        ),
    ]


class AddonDeprecations(OPModel):
    addon_name: Annotated[str, Field(title="Addon name", examples=["core"])]
    addon_version: Annotated[str, Field(title="Addon version", examples=["1.2.3"])]
    deprecations: Annotated[list[DeprecationItem], Field(default_factory=list)]


class DeprecationsModel(OPModel):
    server: Annotated[
        list[DeprecationItem],
        Field(
            default_factory=list,
            title="Server deprecations",
            description="Deprecated features used by the server itself",
        ),
    ]
    addons: Annotated[
        list[AddonDeprecations],
        Field(
            default_factory=list,
            title="Addon deprecations",
            description="Deprecated features used by the addons",
        ),
    ]


def _get_addon_versions() -> dict[tuple[str, str], tuple[str, str]]:
    """Map (addon directory, version directory) to (addon name, version)"""
    result: dict[tuple[str, str], tuple[str, str]] = {}
    for addon_name, definition in AddonLibrary.items():
        for version, addon in definition.versions.items():
            path = os.path.join(os.path.abspath(addon.addon_dir), "")
            if split := split_addon_path(path):
                result[split[:2]] = (addon_name, version)
    return result


def _version_key(version: str) -> tuple[int, semver.VersionInfo | str]:
    """Sort key of addon versions. Non-semver versions go first."""
    try:
        return 1, semver.VersionInfo.parse(version)
    except ValueError:
        return 0, version


def _get_latest_versions() -> set[tuple[str, str]]:
    """Return (addon name, version) of the latest version of each addon"""
    return {
        (addon_name, max(definition.versions, key=_version_key))
        for addon_name, definition in AddonLibrary.items()
        if definition.versions
    }


@router.get("/system/deprecations")
async def get_system_deprecations(
    user: CurrentUser,
    latest: Annotated[
        bool,
        Query(description="Only report the latest version of each addon"),
    ] = False,
) -> DeprecationsModel:
    """Get deprecated features used by the server and addons.

    Deprecations are collected by the worker handling the request.
    All workers import the same addons, so the startup deprecations
    are the same. Deprecations raised at runtime are only reported
    by the worker, which used the deprecated feature.
    """

    if not user.is_admin:
        raise ForbiddenException("Only administrators can see deprecations")

    addon_versions = _get_addon_versions()
    latest_versions = _get_latest_versions() if latest else None
    result = DeprecationsModel(server=[], addons=[])
    addons: dict[tuple[str, str], AddonDeprecations] = {}
    cwd = os.path.join(os.getcwd(), "")

    for record in get_deprecations():
        item = DeprecationItem(
            category=record.category,
            message=record.message,
            file=record.path.removeprefix(cwd),
            line=record.line,
            count=record.count,
        )

        if (split := split_addon_path(record.path)) is None:
            result.server.append(item)
            continue

        addon_dir, version_dir, item.file = split
        # Fall back to directory names for addons, which failed to load
        name, version = addon_versions.get(
            (addon_dir, version_dir),
            (os.path.basename(addon_dir), version_dir),
        )
        if latest_versions is not None and (name, version) not in latest_versions:
            continue
        if (name, version) not in addons:
            addons[name, version] = AddonDeprecations(
                addon_name=name,
                addon_version=version,
                deprecations=[],
            )
        addons[name, version].deprecations.append(item)

    result.addons = [
        addons[key] for key in sorted(addons, key=lambda k: (k[0], _version_key(k[1])))
    ]
    for group in [result.server, *(a.deprecations for a in result.addons)]:
        group.sort(key=lambda item: (item.file, item.line))
    return result

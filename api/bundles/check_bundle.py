from typing import TYPE_CHECKING, Literal

import semver

from ayon_server.addons.library import AddonLibrary
from ayon_server.exceptions import NotFoundException
from ayon_server.types import Field, OPModel
from ayon_server.version import __version__ as ayon_version

from .models import BundleModel, BundlePatchModel

if TYPE_CHECKING:
    pass


def is_compatible(version: str, requirements: str) -> bool:
    conditions = requirements.split(",")
    for condition in conditions:
        condition = condition.strip()
        if not semver.match(version, condition):
            return False
    return True


class BundleIssueModel(OPModel):
    severity: Literal["error", "warning"] = Field(..., example="error")
    addon: str | None = Field(None, example="ftrack")
    message: str = Field(..., example="FTrack addon requires Core >= 1.0.0")


class CheckBundleResponseModel(OPModel):
    success: bool = False
    issues: list[BundleIssueModel] = Field(default_factory=list)

    def message(self):
        if self.success:
            return "Bundle is valid"
        for issue in self.issues:
            if issue.severity == "error":
                msg = f"{issue.addon}: {issue.message}"
        return f"Failed to validate bundle: {msg}"


async def get_active_services() -> list[dict[str, str]]:
    # TODO
    return []


async def check_bundle(
    bundle: BundleModel | BundlePatchModel,
) -> CheckBundleResponseModel:
    issues: list[BundleIssueModel] = []

    if bundle.addons is None:
        return CheckBundleResponseModel(success=True)

    for addon_name, addon_version in bundle.addons.items():
        if addon_version is None:
            continue
        try:
            addon = AddonLibrary.addon(addon_name, addon_version)
        except NotFoundException:
            issues.append(
                BundleIssueModel(
                    severity="error",
                    addon=addon_name,
                    message=f"{addon_name} {addon_version} is not active",
                )
            )
            continue

        if addon.compatibility is None:
            # No compatibility information available,
            # we assume it's compatible with everything.
            continue

        compat = addon.compatibility

        if compat.server_version is not None:
            # Check if the server version is compatible
            if not is_compatible(ayon_version, compat.server_version):
                msg = f"Ayon server {addon.compatibility.server_version} is required"
                issues.append(
                    BundleIssueModel(severity="error", addon=addon_name, message=msg)
                )

        if compat.launcher_version is not None:
            # Check if the launcher version is compatible
            if bundle.installer_version is None:
                issues.append(
                    BundleIssueModel(
                        severity="error",
                        addon=addon_name,
                        message="Launcher is required",
                    )
                )
                continue

            if not is_compatible(bundle.installer_version, compat.launcher_version):
                msg = f"Launcher {compat.launcher_version} is required"
                issues.append(
                    BundleIssueModel(severity="error", addon=addon_name, message=msg)
                )

        for r_name, requirement in (compat.required_addons or {}).items():
            r_version = bundle.addons.get(r_name)
            if r_version is None:
                issues.append(
                    BundleIssueModel(
                        severity="error",
                        addon=addon_name,
                        message=f"{addon_name} is required",
                    )
                )
                continue

            if not is_compatible(r_version, requirement):
                msg = f"{r_name} {requirement} is required"
                issues.append(
                    BundleIssueModel(severity="error", addon=addon_name, message=msg)
                )

        for r_name, requirement in (compat.compatible_addons or {}).items():
            r_version = bundle.addons.get(r_name)
            if r_version is None:
                continue

            if not is_compatible(r_version, requirement):
                msg = f"{r_name} {requirement} is required"
                issues.append(
                    BundleIssueModel(severity="warning", addon=addon_name, message=msg)
                )

    has_errors = any(issue.severity == "error" for issue in issues)
    return CheckBundleResponseModel(success=not has_errors, issues=issues)

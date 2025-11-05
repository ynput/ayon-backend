from datetime import datetime
from typing import Any

from ayon_server.types import NAME_REGEX, Field, OPModel, Platform
from ayon_server.utils import camelize

dependency_packages_meta: dict[str, Any] = {
    "title": "Dependency packages",
    "description": "mapping of platform:dependency_package_filename",
    "example": {
        "windows": "a_windows_package123.zip",
        "linux": "a_linux_package123.zip",
        "darwin": "a_mac_package123.zip",
    },
}


class BaseBundleModel(OPModel):
    pass


class AddonDevelopmentItem(OPModel):
    enabled: bool = Field(
        True, example=False, description="Enable/disable addon development"
    )
    path: str = Field(
        "", example="/path/to/addon", description="Path to addon directory"
    )


class BundleModel(BaseBundleModel):
    """
    Model for GET and POST requests
    """

    name: str = Field(
        ...,
        title="Name",
        description="Name of the bundle",
        example="my_superior_bundle",
        regex=NAME_REGEX,
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        example=datetime.now(),
    )

    ## patchables

    # data
    addons: dict[str, str | None] = Field(
        default_factory=dict,
        title="Addons",
        example={"ftrack": "1.2.3"},
    )
    installer_version: str | None = Field(None, example="1.2.3")
    dependency_packages: dict[Platform, str | None] = Field(
        default_factory=dict,
        **dependency_packages_meta,
    )
    addon_development: dict[str, AddonDevelopmentItem] = Field(
        default_factory=dict,
        example={"ftrack": {"enabled": True, "path": "~/devel/ftrack"}},
    )

    # flags
    is_production: bool = Field(False, example=False)
    is_staging: bool = Field(False, example=False)
    is_archived: bool = Field(False, example=False)
    is_dev: bool = Field(False, example=False)
    is_project: bool = Field(False, example=False)
    active_user: str | None = Field(None, example="admin")


class BundlePatchModel(BaseBundleModel):
    addons: dict[str, str | None] | None = Field(
        None,
        title="Addons",
        example={"ftrack": None, "kitsu": "1.2.3"},
    )
    installer_version: str | None = Field(None, example="1.2.3")
    dependency_packages: dict[Platform, str | None] | None = Field(
        None,
        **dependency_packages_meta,
    )
    is_production: bool | None = Field(None, example=False)
    is_staging: bool | None = Field(None, example=False)
    is_archived: bool | None = Field(None, example=False)
    is_dev: bool | None = Field(None, example=False)
    active_user: str | None = Field(None, example="admin")
    addon_development: dict[str, AddonDevelopmentItem] | None = Field(None)

    def get_changed_fields(self) -> list[str]:
        dict_data = self.dict(exclude_none=True)
        return [camelize(field) for field in dict_data.keys()]

    def get_changes_description(self, bundle_name: str) -> str:
        description = f"Bundle '{bundle_name}' has been "
        changes = []

        if self.is_production is not None:
            changes.append(
                "set as production" if self.is_production else "unset as production"
            )

        if self.is_staging is not None:
            changes.append("set as staging" if self.is_staging else "unset as staging")

        if self.is_archived is not None:
            changes.append("archived" if self.is_archived else "unarchived")

        if self.is_dev is not None:
            changes.append(
                "set as development" if self.is_dev else "unset as development"
            )

        if self.addons is not None:
            changes.append("updated with new addons")

        if self.installer_version is not None:
            changes.append("updated with a new installer version")

        if self.dependency_packages is not None:
            changes.append("updated with new dependency packages")

        if changes and len(changes) < 3:
            if len(changes) > 1:
                description += ", ".join(changes[:-1]) + ", and " + changes[-1] + "."
            else:
                description += changes[0] + "."
        else:
            description += "updated."
        return description


class ListBundleModel(OPModel):
    bundles: list[BundleModel] = Field(default_factory=list)
    production_bundle: str | None = Field(None, example="my_superior_bundle")
    staging_bundle: str | None = Field(None, example="my_superior_bundle")
    dev_bundles: list[str] = Field(default_factory=list)

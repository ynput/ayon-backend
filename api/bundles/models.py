import re
from datetime import datetime

from pydantic import ConfigDict, RootModel, field_validator

from ayon_server.logging import logger
from ayon_server.types import NAME_REGEX, SEMVER_REGEX, Field, OPModel, Platform
from ayon_server.utils import camelize


class DependencyPackagesModel(RootModel[dict[Platform, str | None]]):
    """Mapping of platforms to dependency package filenames."""

    model_config = ConfigDict(
        title="Dependency packages",
        json_schema_extra={
            "examples": [
                {
                    "windows": "a_windows_package123.zip",
                    "linux": "a_linux_package123.zip",
                    "darwin": "a_mac_package123.zip",
                }
            ]
        },
    )

    root: dict[Platform, str | None] = Field(default_factory=dict)


class BaseBundleModel(OPModel):
    pass


class AddonDevelopmentItem(OPModel):
    enabled: bool = Field(
        True, example=False, description="Enable/disable addon development"
    )
    path: str = Field(
        "", example="/path/to/addon", description="Path to addon directory"
    )


class BundleDataModel(BaseBundleModel):
    """Stored bundle data."""

    description: str | None = Field(None, title="Description")
    is_project: bool = Field(False, example=False)
    addons: dict[str, str | None] = Field(
        default_factory=dict,
        title="Addons",
        example={"ftrack": "1.2.3"},
    )

    @field_validator("addons")
    @classmethod
    def validate_addons(cls, value: dict[str, str | None]) -> dict[str, str | None]:
        for addon_name, version in value.items():
            if version is None:
                continue
            if version.lower() == "none":
                value[addon_name] = None
                continue
            if version in ["__inherit__", "__disable__"]:
                continue
            if not re.match(SEMVER_REGEX, version):
                logger.warning(
                    f"Version '{version}' for addon '{addon_name}'"
                    " is not a valid semantic version."
                )
        return value

    installer_version: str | None = Field(None, example="1.2.3")
    dependency_packages: DependencyPackagesModel = Field(
        default_factory=DependencyPackagesModel,
    )
    addon_development: dict[str, AddonDevelopmentItem] = Field(
        default_factory=dict,
        example={"ftrack": {"enabled": True, "path": "~/devel/ftrack"}},
    )


class BundleModel(BundleDataModel):
    """Flat model for GET and POST requests."""

    name: str = Field(
        ...,
        title="Name",
        description="Name of the bundle",
        example="my_superior_bundle",
        pattern=NAME_REGEX,
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        example=datetime.now(),
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        example=datetime.now(),
    )

    def to_data(self, stored_data: BundleDataModel | None = None) -> BundleDataModel:
        data = stored_data.model_dump(by_alias=False) if stored_data else {}
        data.update(
            self.model_dump(include=set(BundleDataModel.model_fields), by_alias=False)
        )
        return BundleDataModel.model_validate(data)

    # flags
    is_production: bool = Field(False, example=False)
    is_staging: bool = Field(False, example=False)
    is_archived: bool = Field(False, example=False)
    is_dev: bool = Field(False, example=False)
    active_user: str | None = Field(None, example="admin")


class BundlePatchModel(BaseBundleModel):
    description: str | None = Field(None, title="Description")
    addons: dict[str, str | None] | None = Field(
        None,
        title="Addons",
        example={"ftrack": None, "kitsu": "1.2.3"},
    )

    @field_validator("addons")
    @classmethod
    def validate_addons(
        cls, value: dict[str, str | None] | None
    ) -> dict[str, str | None] | None:
        if value is None:
            return value
        for addon_name, version in value.items():
            if version is None:
                continue
            if version.lower() == "none":
                value[addon_name] = None
                continue
            if version in ["__inherit__", "__disable__"]:
                continue
            if not re.match(SEMVER_REGEX, version):
                raise ValueError(
                    f"Version '{version}' for addon '{addon_name}'"
                    " is not a valid semantic version."
                )
        return value

    installer_version: str | None = Field(None, example="1.2.3")
    dependency_packages: DependencyPackagesModel | None = Field(None)
    is_production: bool | None = Field(None, example=False)
    is_staging: bool | None = Field(None, example=False)
    is_archived: bool | None = Field(None, example=False)
    is_dev: bool | None = Field(None, example=False)
    active_user: str | None = Field(None, example="admin")
    addon_development: dict[str, AddonDevelopmentItem] | None = Field(None)

    def get_changed_fields(self) -> list[str]:
        dict_data = self.model_dump(exclude_none=True)
        if "description" in self.model_fields_set:
            dict_data["description"] = self.description
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

        if "description" in self.model_fields_set:
            changes.append("updated with a new description")

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

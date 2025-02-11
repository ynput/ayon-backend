from typing import Any, Literal

from pydantic import validator

from ayon_server.types import Field, OPModel, Platform

# For type=server, we do not use absolute url, because base server url can
# be different for different users. Instead, we provide just the information
# the source is availabe and the client can construct the url from the
# filename attribute of BasePackageModel
# e.g. http://server/api/desktop/{installers|dependency_packages}/{filename}
# type = url is deprecated!


class SourceModel(OPModel):
    type: Literal["server", "http"] = Field(
        ...,
        title="Source type",
        description="If set to server, the file is stored on the server. "
        "If set to http, the file is downloaded from the specified URL.",
        example="url",
    )
    url: str | None = Field(
        None,
        title="Download URL",
        description="URL to download the file from. Only used if type is url",
        example="https://example.com/file.zip",
    )

    @validator("type", pre=True)
    def validate_type(cls, value: Any):
        # if type is "url", change it to "http"
        if value == "url":
            return "http"
        return value


SOURCES_META = Field(
    default_factory=list,
    title="Sources",
    description="List of sources to download the file from. "
    "Server source is added automatically by the server if the file is uploaded.",
    example=[{"type": "url"}],
)


class BasePackageModel(OPModel):
    filename: str
    platform: Platform
    size: int | None = None
    checksum: str | None = None
    checksum_algorithm: Literal["md5", "sha1", "sha256"] | None = None
    sources: list[SourceModel] = SOURCES_META


class SourcesPatchModel(OPModel):
    sources: list[SourceModel] = SOURCES_META


class DependencyPackageManifest(BasePackageModel):
    installer_version: str = Field(
        ...,
        title="Installer version",
        description="Version of the Ayon installer this package is created with",
        example="1.2.3",
    )
    source_addons: dict[str, str | None] = Field(
        default_factory=dict,
        title="Source addons",
        description="mapping of addon_name:addon_version used to create the package",
        example={"ftrack": "1.2.3", "maya": "2.4"},
    )
    python_modules: dict[str, str | dict[str, str]] = Field(
        default_factory=dict,
        title="Python modules",
        description="mapping of module_name:module_version used to create the package",
        example={"requests": "2.25.1", "pydantic": "1.8.2"},
    )


class InstallerManifest(BasePackageModel):
    version: str = Field(
        ...,
        title="Version",
        description="Version of the installer",
        example="1.2.3",
    )
    python_version: str = Field(
        ...,
        title="Python version",
        description="Version of Python that the installer is created with",
        example="3.11",
    )
    python_modules: dict[str, str | dict[str, str]] = Field(
        default_factory=dict,
        title="Python modules",
        description="mapping of module name:version used to create the installer",
        example={"requests": "2.25.1", "pydantic": "1.8.2"},
    )
    runtime_python_modules: dict[str, str] = Field(
        default_factory=dict,
        title="Runtime Python modules",
        description="mapping of module_name:module_version used to run the installer",
        example={"requests": "2.25.1", "pydantic": "1.8.2"},
    )

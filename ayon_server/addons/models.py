from typing import Annotated, Literal, NotRequired, TypedDict

from ayon_server.types import Field, OPModel

SourceType = Literal["filesystem", "server", "http"]


class ClientSourceInfo(OPModel):
    type: SourceType


class PathDefinition(OPModel):
    windows: str = ""
    linux: str = ""
    darwin: str = ""


class FilesystemSourceInfo(ClientSourceInfo):
    type: Literal["filesystem"] = "filesystem"
    path: PathDefinition = Field(default_factory=lambda: PathDefinition())


class ServerSourceInfo(ClientSourceInfo):
    type: Literal["server"] = "server"
    filename: str | None = None
    path: str | None = None


class HttpSourceInfo(ClientSourceInfo):
    type: Literal["http"] = "http"
    url: str
    filename: str | None = None
    headers: dict[str, str] | None = None


class SSOOption(OPModel):
    name: Annotated[
        str,
        Field(
            title="Provider name",
            description="Unique name of the SSO provider",
        ),
    ]

    hidden: Annotated[
        bool,
        Field(
            title="Hidden",
            description="If True, the provider will not be shown in the UI",
        ),
    ] = False

    title: Annotated[
        str | None,
        Field(
            description="Nice human-readable title of the provider",
        ),
    ] = None

    icon: Annotated[
        str | None,
        Field(
            title="Icon",
        ),
    ] = None

    color: Annotated[
        str,
        Field(
            title="Button background color",
        ),
    ] = "#47b7da"

    text_color: Annotated[
        str,
        Field(
            title="Button text color",
        ),
    ] = "#ffffff"

    redirect_key: str | None = None
    url: str
    args: dict[str, str] = Field(default_factory=dict)
    callback: str = Field(...)


SourceInfo = FilesystemSourceInfo | ServerSourceInfo | HttpSourceInfo
SourceInfoTypes = (FilesystemSourceInfo, ServerSourceInfo, HttpSourceInfo)


FrontendScope = Literal["settings", "project", "dashboard"]


class FrontendScopeSettings(TypedDict):
    admin: NotRequired[bool]  # Available for admin users only
    manager: NotRequired[bool]  # Available for manager users only
    sidebar: NotRequired[str]  # Sidebar name


# FrontendScopes is a dictionary that maps frontend scope names
# (e.g., "settings", "project", "dashboard") to their respective settings,
# which define access and display properties for different user roles.
FrontendScopes = dict[FrontendScope, FrontendScopeSettings]
FrontendModules = dict[str, list[str]]

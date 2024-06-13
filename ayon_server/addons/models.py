from typing import Literal

from ayon_server.types import Field, OPModel


class ClientSourceInfo(OPModel):
    type: Literal["filesystem", "server", "http"] = Field(...)


class PathDefinition(OPModel):
    windows: str = ""
    linux: str = ""
    darwin: str = ""


class FilesystemSourceInfo(ClientSourceInfo):
    type: Literal["filesystem"] = Field("filesystem")
    path: PathDefinition = Field(default_factory=lambda: PathDefinition())


class ServerSourceInfo(ClientSourceInfo):
    type: Literal["server"] = Field("server")
    filename: str | None = Field(None)
    path: str | None = Field(None)


class HttpSourceInfo(ClientSourceInfo):
    type: Literal["http"] = Field("http")
    url: str
    filename: str | None = Field(None)
    headers: dict[str, str] | None = Field(None)


class SSOOption(OPModel):
    name: str = Field(...)
    title: str | None = Field(None)
    icon: str | None = Field(None)
    color: str = Field("#47b7da")
    text_color: str = Field("#ffffff")
    redirect_key: str | None = Field(None)
    url: str = Field(...)
    args: dict[str, str] = Field(default_factory=dict)
    callback: str = Field(...)


SourceInfo = FilesystemSourceInfo | ServerSourceInfo | HttpSourceInfo
SourceInfoTypes = (FilesystemSourceInfo, ServerSourceInfo, HttpSourceInfo)

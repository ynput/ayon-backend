from typing import Literal

from ayon_server.types import Field, OPModel


class ClientSourceInfo(OPModel):
    type: Literal["filesystem", "server", "http"] = Field(...)


class PathDefinition(OPModel):
    windows: str
    linux: str
    darwin: str


class FilesystemSourceInfo(ClientSourceInfo):
    type: Literal["filesystem"] = Field("filesystem")
    path: PathDefinition = Field(default_factory=PathDefinition)


class ServerSourceInfo(ClientSourceInfo):
    type: Literal["server"] = Field("server")
    filename: str | None = Field(None)
    path: str | None = Field(None)


class HttpSourceInfo(ClientSourceInfo):
    type: Literal["http"] = Field("http")
    url: str
    headers: dict[str, str] | None = Field(None)


SourceInfo = FilesystemSourceInfo | ServerSourceInfo | HttpSourceInfo

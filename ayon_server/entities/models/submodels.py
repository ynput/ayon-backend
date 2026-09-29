from typing import Any, Literal

from pydantic import Field

from ayon_server.types import OPModel


class RepresentationFileModel(OPModel):
    id: str = Field(
        ...,
        title="File ID",
        description="Unique (within the representation) ID of the file",
        example="7da4cba0f3e0b3c0aeac10d5bc73dcab",
    )
    name: str | None = Field(None, title="File name", description="File name")
    path: str = Field(
        ...,
        title="File path",
        description="Path to the file",
        example="{root}/demo_Commercial/shots/sh010/workfile/"
        "workfileCompositing/v001/sh010_workfile Compositing_v001.ma",
    )
    size: int = Field(
        0,
        title="File size",
        description="Size of the file in bytes",
        example="123456",
    )
    hash: str | None = Field(
        None,
        title="Hash of the file",
        example="e831c13f0ba0fbbfe102cd50420439d1",
    )
    hash_type: Literal["md5", "sha1", "sha256", "op3"] = Field(
        "md5",
        title="Hash type. 'op3' is the default for OpenPype 3 imports",
        example="md5",
    )


class LinkTypeModel(OPModel):
    name: str = Field(..., description="Name of the link type")
    link_type: str = Field(..., description="Type of the link")
    input_type: str = Field(..., description="Input entity type")
    output_type: str = Field(..., description="Output entity type")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional link type data",
    )

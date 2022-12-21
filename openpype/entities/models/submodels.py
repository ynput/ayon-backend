from typing import Literal

from pydantic import BaseModel, Field


class RepresentationFile(BaseModel):
    id: str = Field(
        ...,
        title="File ID",
        description="Unique (within the representation) ID of the file",
        example="7da4cba0f3e0b3c0aeac10d5bc73dcab",
    )
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
    hash_type: Literal["md5", "sha1", "sha256"] = Field(
        "md5",
        title="Hash type",
        example="md5",
    )

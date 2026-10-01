from typing import Annotated, Any, Literal

from ayon_server.types import Field, OPModel


class RepresentationFileModel(OPModel):
    id: Annotated[
        str,
        Field(
            title="File ID",
            description="Unique (within the representation) ID of the file",
            examples=["7da4cba0f3e0b3c0aeac10d5bc73dcab"],
        ),
    ]

    name: Annotated[
        str | None,
        Field(
            title="File name",
            description="File name",
        ),
    ] = None

    path: Annotated[
        str,
        Field(
            title="File path",
            description="Path to the file",
            examples=[
                "{root}/demo_Commercial/shots/sh010/workfile/"
                "workfileCompositing/v001/sh010_workfile Compositing_v001.ma"
            ],
        ),
    ]

    size: Annotated[
        int,
        Field(
            title="File size",
            description="Size of the file in bytes",
            examples=["123456"],
        ),
    ] = 0

    hash: Annotated[
        str | None,
        Field(
            title="Hash of the file",
            examples=["e831c13f0ba0fbbfe102cd50420439d1"],
        ),
    ] = None

    hash_type: Annotated[
        Literal["md5", "sha1", "sha256", "op3"],
        Field(
            title="Hash type",
            description="'op3' is the default for OpenPype 3 imports",
            example="md5",
        ),
    ] = "md5"


class LinkTypeModel(OPModel):
    name: Annotated[str, Field(description="Name of the link type")]
    link_type: Annotated[str, Field(description="Type of the link")]
    input_type: Annotated[str, Field(description="Input entity type")]
    output_type: Annotated[str, Field(description="Output entity type")]
    data: Annotated[
        dict[str, Any],
        Field(
            default_factory=dict,
            description="Additional link type data",
        ),
    ]

from typing import Literal

from ayon_server.types import Field, OPModel
from ayon_server.utils import create_uuid

ReviewableType = Literal["image", "video"]


class ReviewableModel(OPModel):
    id: str = Field(default=create_uuid(), title="Reviewable ID")
    name: str = Field(..., title="Reviewable Name")
    type: ReviewableType = Field(..., title="Reviewable Type")


class ReviewableListModel(OPModel):
    reviewables: list[ReviewableModel]

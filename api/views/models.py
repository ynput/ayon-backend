from typing import Annotated, Any, Literal

from pydantic import Field

from ayon_server.types import OPModel
from ayon_server.utils import create_uuid

#
# Shared types and fields
#

ViewScopes = Literal["overview"]

FViewId = Annotated[str, Field(title="View ID", default_factory=create_uuid)]
FViewLabel = Annotated[str, Field(title="View label")]
FViewScope = Annotated[ViewScopes, Field(title="View scope", default="overview")]

# Shared submodels


class ColumnItemModel(OPModel):
    name: Annotated[str, Field(title="Column name")]
    pinned: Annotated[bool, Field(title="Is column pinned")] = False
    width: Annotated[int | None, Field(title="Column width")] = None


#
# Per-page models
#


class OverviewSettings(OPModel):
    filter: dict[str, Any] | None = None
    columns: Annotated[
        list[ColumnItemModel], Field(title="List of columns", default_factory=list)
    ]


#
# Actual REST API models
#


class ViewModel(OPModel):
    id: FViewId
    label: FViewLabel
    owner: str
    settings: OverviewSettings | None = None


class ViewListItemModel(OPModel):
    """View list item model."""

    id: FViewId
    label: FViewLabel


class ViewListPostModel(OPModel):
    id: FViewId | None = None
    label: FViewLabel


class ViewListModel(OPModel):
    views: Annotated[list[ViewListItemModel], Field(title="List of views")]

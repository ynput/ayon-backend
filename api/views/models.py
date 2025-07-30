from typing import Annotated, Any, Literal

from pydantic import Field

from ayon_server.sqlfilter import QueryFilter
from ayon_server.types import OPModel
from ayon_server.utils import create_uuid

#
# Shared types and fields
#

ViewScopes = Literal["project", "studio"]
ViewType = Literal["overview", "tasks"]

FViewScope = Annotated[ViewScopes, Field(title="View scope", example="project")]
FViewType = Annotated[ViewType, Field(title="View type", example="overview")]

FViewId = Annotated[str, Field(title="View ID", default_factory=create_uuid)]
FViewLabel = Annotated[str, Field(title="View label", example="To review")]
FViewOwner = Annotated[str, Field(title="View owner", example="steve")]
FViewPrivate = Annotated[bool, Field(title="Is view private")]
FViewVisibilty = Annotated[Literal["public", "private"], Field(title="View visibility")]

#
# View list models
#


class ViewListItemModel(OPModel):
    """View list item model."""

    id: FViewId
    label: FViewLabel
    scope: FViewScope = "studio"
    position: int = 0
    owner: FViewOwner | None = None
    visibility: FViewVisibilty = "private"
    personal: bool = True


class ViewListModel(OPModel):
    views: Annotated[list[ViewListItemModel], Field(title="List of views")]


# Shared submodels


class ColumnItemModel(OPModel):
    name: Annotated[str, Field(title="Column name")]
    pinned: Annotated[bool, Field(title="Is column pinned")] = False
    width: Annotated[int | None, Field(title="Column width")] = None


#
# Per-page models
#


class OverviewSettings(OPModel):
    filter: QueryFilter | None = None
    columns: Annotated[
        list[ColumnItemModel],
        Field(
            title="List of columns",
            default_factory=list,
            example=[
                "name",
                "status",
                "assignees",
                "attrib.priority",
            ],
        ),
    ]


class TaskProgressSettings(OPModel):
    expanded: bool = False
    filter: QueryFilter | None = None


#
# Actual REST API models
#


class BaseViewModel(ViewListItemModel):
    settings: OverviewSettings | TaskProgressSettings


class OverviewViewModel(BaseViewModel):
    """Overview view model."""

    view_type: Literal["overview"] = "overview"
    settings: OverviewSettings


class TaskProgressViewModel(BaseViewModel):
    """Task progress view model."""

    view_type: Literal["taskProgress"] = "taskProgress"
    settings: TaskProgressSettings


# Compound models


ViewModel = Annotated[
    OverviewViewModel | TaskProgressViewModel,
    Field(
        discriminator="view_type",
        title="View model",
    ),
]


def construct_view_model(**data: Any) -> ViewModel:
    if data.get("view_type") == "overview":
        return OverviewViewModel(**data)
    elif data.get("view_type") == "taskProgress":
        return TaskProgressViewModel(**data)
    raise ValueError("Invalid view type provided")

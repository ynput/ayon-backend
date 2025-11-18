from typing import Annotated, Any, Literal

from pydantic import Field

from ayon_server.sqlfilter import QueryFilter
from ayon_server.types import OPModel
from ayon_server.utils import create_uuid

#
# Shared types and fields
#

ViewScopes = Literal["project", "studio"]
ViewType = Literal[
    "overview",
    "taskProgress",
    "lists",
    "reviews",
    "versions",
    "reports",
    "scheduler",
    "planner",
]

FViewScope = Annotated[
    ViewScopes,
    Field(
        title="View scope",
        description=(
            "Determines whether the view is only available "
            "for the given project or for all projects (studio)."
        ),
        example="project",
    ),
]

FViewType = Annotated[
    ViewType,
    Field(
        title="View type",
        description=(
            "View type specifies which page in the frontend this view is used for. "
            "Every view type has its own settings data structure."
        ),
        example="overview",
    ),
]

FViewId = Annotated[
    str,
    Field(
        title="View ID",
        description="Unique identifier for the view within the given scope.",
        default_factory=create_uuid,
    ),
]

FViewLabel = Annotated[
    str,
    Field(
        title="View label",
        description="Human-readable name of the view.",
        example="To review",
    ),
]

FViewOwner = Annotated[
    str,
    Field(
        title="View owner",
        description=(
            "Name of the user who created the view. "
            "Owners have full control over the view, "
        ),
        example="steve",
    ),
]

FViewWorking = Annotated[
    bool,
    Field(
        title="Working view",
        description=(
            "Working view is a special type of the view that "
            "automatically stores the current view settings "
            "without explicitly saving them. "
            "Working views are always private and scoped to the project "
        ),
    ),
]

FViewVisibility = Annotated[
    Literal["public", "private"],
    Field(
        title="View visibility",
        description=(
            "Visibility of the view. "
            "Public views are visible to all users, "
            "private views are only visible to the owner."
        ),
    ),
]


# Shared submodels


class ColumnItemModel(OPModel):
    name: Annotated[str, Field(title="Column name")]
    visible: Annotated[bool, Field(title="Is column visible")] = True
    pinned: Annotated[bool, Field(title="Is column pinned")] = False
    width: Annotated[int | None, Field(title="Column width")] = None


FColumnList = Annotated[
    list[ColumnItemModel],
    Field(
        title="List of columns",
        default_factory=list,
        example=[
            {"name": "name", "pinned": True, "width": 120},
            {"name": "status", "pinned": True, "width": 120},
            {"name": "assignees", "width": 120},
            {"name": "attrib.priority", "width": 120},
        ],
    ),
]


#
# Per-page models
#


class OverviewSettings(OPModel):
    show_hierarchy: bool = True
    row_height: int | None = None
    group_by: str | None = None
    show_empty_groups: bool = False
    sort_by: str | None = None
    sort_desc: bool = False
    filter: QueryFilter | None = None
    columns: FColumnList


class TaskProgressSettings(OPModel):
    filter: QueryFilter | None = None
    columns: FColumnList


class ListsSettings(OPModel):
    row_height: int | None = None
    sort_by: str | None = None
    sort_desc: bool = False
    filter: QueryFilter | None = None
    columns: FColumnList


class ReviewsSettings(ListsSettings):
    pass


class VersionsSettings(OPModel):
    show_products: bool = False
    row_height: int | None = None
    show_grid: bool = True
    grid_height: int | None = None
    featured_version_order: list[str] | None = None
    slicer_type: str | None = None
    group_by: str | None = None
    show_empty_groups: bool = False
    sort_by: str | None = None
    sort_desc: bool = False
    filter: QueryFilter | None = None
    columns: FColumnList


class ReportsSettings(OPModel):
    widgets: Annotated[
        list[dict[str, Any]],
        Field(title="List of report widgets", default_factory=list),
    ]
    date_format: str | None = None


class RangeModel(OPModel):
    start: int
    end: int


class SchedulerSettings(OPModel):
    show_hierarchy: bool = True
    row_height: int | None = None
    group_by: str | None = None
    show_empty_groups: bool = False
    sort_by: str | None = None
    sort_desc: bool = False
    filter: QueryFilter | None = None
    columns: FColumnList
    range: RangeModel | None = None
    color_by: str | None = None
    show_planner: bool = False
    scenario: str | None = None
    panel_width: int | None = None


class PlannerSettings(OPModel):
    filter: QueryFilter | None = None
    range: RangeModel | None = None
    group_by: str | None = None
    group_by_desc: bool = False
    sort_by: str | None = None
    sort_by_desc: bool = False
    sort_by_tracks: str | None = None
    sort_by_tracks_desc: bool = False
    color_by: str | None = None
    scenario: str | None = None
    panel_width: int | None = None


ViewSettingsModel = (
    OverviewSettings
    | TaskProgressSettings
    | ListsSettings
    | VersionsSettings
    | ReportsSettings
    | ReviewsSettings
    | SchedulerSettings
    | PlannerSettings
)

from typing import Annotated, Any, Literal

from pydantic import Field

from ayon_server.types import OPModel
from ayon_server.views.models import (
    FViewId,
    FViewLabel,
    FViewOwner,
    FViewScope,
    FViewVisibility,
    FViewWorking,
    ListsSettings,
    OverviewSettings,
    PlannerSettings,
    ReportsSettings,
    ReviewsSettings,
    SchedulerSettings,
    TaskProgressSettings,
    VersionsSettings,
    ViewSettingsModel,
)

#
# View list models
#


class ViewListItemModel(OPModel):
    """View list item model."""

    id: FViewId
    label: FViewLabel
    scope: FViewScope
    owner: FViewOwner
    visibility: FViewVisibility
    working: FViewWorking
    position: int
    access_level: int


class ViewListModel(OPModel):
    views: Annotated[list[ViewListItemModel], Field(title="List of views")]


#
# GET REST API models
#


class BaseViewModel(ViewListItemModel):
    settings: ViewSettingsModel
    access: dict[str, Any]


class OverviewViewModel(BaseViewModel):
    """Overview view model."""

    view_type: Literal["overview"] = "overview"
    settings: OverviewSettings


class TaskProgressViewModel(BaseViewModel):
    """Task progress view model."""

    view_type: Literal["taskProgress"] = "taskProgress"
    settings: TaskProgressSettings


class ListsViewModel(BaseViewModel):
    """Lists view model."""

    view_type: Literal["lists"] = "lists"
    settings: ListsSettings


class ReviewsViewModel(BaseViewModel):
    """Reviews view model."""

    view_type: Literal["reviews"] = "reviews"
    settings: ReviewsSettings


class VersionsViewModel(BaseViewModel):
    """Versions view model."""

    view_type: Literal["versions"] = "versions"
    settings: VersionsSettings


class ReportsViewModel(BaseViewModel):
    """Reports view model."""

    view_type: Literal["reports"] = "reports"
    settings: ReportsSettings


class SchedulerViewModel(BaseViewModel):
    """Scheduler view model."""

    view_type: Literal["scheduler"] = "scheduler"
    settings: SchedulerSettings


class PlannerViewModel(BaseViewModel):
    """Planner view model."""

    view_type: Literal["planner"] = "planner"
    settings: PlannerSettings


#
# POST REST API models
#


class BaseViewPostModel(OPModel):
    id: FViewId
    label: FViewLabel
    working: FViewWorking = True
    settings: ViewSettingsModel


class OverviewViewPostModel(BaseViewPostModel):
    """Overview view post model."""

    _view_type: Literal["overview"] = "overview"
    settings: OverviewSettings


class TaskProgressViewPostModel(BaseViewPostModel):
    """Task progress view post model."""

    _view_type: Literal["taskProgress"] = "taskProgress"
    settings: TaskProgressSettings


class ListsViewPostModel(BaseViewPostModel):
    """Lists view post model."""

    _view_type: Literal["lists"] = "lists"
    settings: ListsSettings


class ReviewsViewPostModel(BaseViewPostModel):
    """Reviews view post model."""

    _view_type: Literal["reviews"] = "reviews"
    settings: ReviewsSettings


class VersionsViewPostModel(BaseViewPostModel):
    """Versions view post model."""

    _view_type: Literal["versions"] = "versions"
    settings: VersionsSettings


class ReportsViewPostModel(BaseViewPostModel):
    """Reports view post model."""

    _view_type: Literal["reports"] = "reports"
    settings: ReportsSettings


class SchedulerViewPostModel(BaseViewPostModel):
    """Scheduler view post model."""

    _view_type: Literal["scheduler"] = "scheduler"
    settings: SchedulerSettings


class PlannerViewPostModel(BaseViewPostModel):
    """Planner view post model."""

    _view_type: Literal["planner"] = "planner"
    settings: PlannerSettings


#
# Patch REST API models
#


class BaseViewPatchModel(OPModel):
    label: FViewLabel | None = None
    owner: FViewOwner | None = None
    settings: ViewSettingsModel | None = None


class OverviewViewPatchModel(BaseViewPatchModel):
    """Overview view post model."""

    _view_type: Literal["overview"] = "overview"
    settings: OverviewSettings | None = None


class TaskProgressViewPatchModel(BaseViewPatchModel):
    """Task progress view post model."""

    _view_type: Literal["taskProgress"] = "taskProgress"
    settings: TaskProgressSettings | None = None


class ListsViewPatchModel(BaseViewPatchModel):
    """Lists view post model."""

    _view_type: Literal["lists"] = "lists"
    settings: ListsSettings | None = None


class ReviewsViewPatchModel(BaseViewPatchModel):
    """Reviews view post model."""

    _view_type: Literal["reviews"] = "reviews"
    settings: ReviewsSettings | None = None


class VersionsViewPatchModel(BaseViewPatchModel):
    """Versions view post model."""

    _view_type: Literal["versions"] = "versions"
    settings: VersionsSettings | None = None


class ReportsViewPatchModel(BaseViewPatchModel):
    """Reports view post model."""

    _view_type: Literal["reports"] = "reports"
    settings: ReportsSettings | None = None


class SchedulerViewPatchModel(BaseViewPatchModel):
    """Scheduler view post model."""

    _view_type: Literal["scheduler"] = "scheduler"
    settings: SchedulerSettings | None = None


class PlannerViewPatchModel(BaseViewPatchModel):
    """Planner view post model."""

    _view_type: Literal["planner"] = "planner"
    settings: PlannerSettings | None = None


#
# Compound models
#


ViewModel = Annotated[
    OverviewViewModel
    | TaskProgressViewModel
    | ListsViewModel
    | ReviewsViewModel
    | VersionsViewModel
    | ReportsViewModel
    | SchedulerViewModel
    | PlannerViewModel,
    Field(
        discriminator="_view_type",
        title="View model",
    ),
]

ViewPostModel = Annotated[
    OverviewViewPostModel
    | TaskProgressViewPostModel
    | ListsViewPostModel
    | ReviewsViewPostModel
    | VersionsViewPostModel
    | ReportsViewPostModel
    | SchedulerViewPostModel
    | PlannerViewPostModel,
    Field(
        discriminator="_view_type",
        title="View post model",
    ),
]

ViewPatchModel = Annotated[
    OverviewViewPatchModel
    | TaskProgressViewPatchModel
    | ListsViewPatchModel
    | ReviewsViewPatchModel
    | VersionsViewPatchModel
    | ReportsViewPatchModel
    | SchedulerViewPatchModel
    | PlannerViewPatchModel,
    Field(
        discriminator="_view_type",
        title="View model",
    ),
]


def construct_view_model(**data: Any) -> ViewModel:
    if data.get("view_type") == "overview":
        return OverviewViewModel(**data)
    elif data.get("view_type") == "taskProgress":
        return TaskProgressViewModel(**data)
    elif data.get("view_type") == "lists":
        return ListsViewModel(**data)
    elif data.get("view_type") == "reviews":
        return ReviewsViewModel(**data)
    elif data.get("view_type") == "versions":
        return VersionsViewModel(**data)
    elif data.get("view_type") == "reports":
        return ReportsViewModel(**data)
    elif data.get("view_type") == "scheduler":
        return SchedulerViewModel(**data)
    elif data.get("view_type") == "planner":
        return PlannerViewModel(**data)
    raise ValueError("Invalid view type provided")


def get_post_model_class(view_type: str) -> type[ViewPostModel]:
    if view_type == "overview":
        return OverviewViewPostModel
    elif view_type == "taskProgress":
        return TaskProgressViewPostModel
    elif view_type == "lists":
        return ListsViewPostModel
    elif view_type == "reviews":
        return ReviewsViewPostModel
    elif view_type == "versions":
        return VersionsViewPostModel
    elif view_type == "reports":
        return ReportsViewPostModel
    elif view_type == "scheduler":
        return SchedulerViewPostModel
    elif view_type == "planner":
        return PlannerViewPostModel
    raise ValueError("Invalid view type provided")


def get_patch_model_class(view_type: str) -> type[ViewPatchModel]:
    if view_type == "overview":
        return OverviewViewPatchModel
    elif view_type == "taskProgress":
        return TaskProgressViewPatchModel
    elif view_type == "lists":
        return ListsViewPatchModel
    elif view_type == "reviews":
        return ReviewsViewPatchModel
    elif view_type == "versions":
        return VersionsViewPatchModel
    elif view_type == "reports":
        return ReportsViewPatchModel
    elif view_type == "scheduler":
        return SchedulerViewPatchModel
    elif view_type == "planner":
        return PlannerViewPatchModel
    raise ValueError("Invalid view type provided")

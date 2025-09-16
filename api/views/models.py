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
    ReviewsSettings,
    TaskProgressSettings,
    TasksSettings,
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

    _view_type: Literal["overview"] = "overview"
    settings: OverviewSettings


class TasksViewModel(BaseViewModel):
    """Tasks view model."""

    _view_type: Literal["tasks"] = "tasks"
    settings: TasksSettings


class TaskProgressViewModel(BaseViewModel):
    """Task progress view model."""

    _view_type: Literal["taskProgress"] = "taskProgress"
    settings: TaskProgressSettings


class ListsViewModel(BaseViewModel):
    """Lists view model."""

    _view_type: Literal["lists"] = "lists"
    settings: ListsSettings


class ReviewsViewModel(BaseViewModel):
    """Reviews view model."""

    _view_type: Literal["reviews"] = "reviews"
    settings: ReviewsSettings


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


class TasksViewPostModel(BaseViewPostModel):
    """Tasks view post model."""

    _view_type: Literal["tasks"] = "tasks"
    settings: TasksSettings


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


class TasksViewPatchModel(BaseViewPatchModel):
    """Tasks view post model."""

    _view_type: Literal["tasks"] = "tasks"
    settings: TasksSettings | None = None


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


#
# Compound models
#


ViewModel = Annotated[
    OverviewViewModel
    | TaskProgressViewModel
    | ListsViewModel
    | ReviewsViewModel
    | TasksViewModel,
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
    | TasksViewPostModel,
    Field(
        discriminator="_view_type",
        title="View post model",
    ),
]

ViewPatchModel = Annotated[
    OverviewViewPatchModel
    | TaskProgressViewPatchModel
    | ListsViewPatchModel
    | ReviewsViewPatchModel,
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
    elif data.get("view_type") == "tasks":
        return TasksViewModel(**data)
    elif data.get("view_type") == "lists":
        return ListsViewModel(**data)
    elif data.get("view_type") == "reviews":
        return ReviewsViewModel(**data)
    raise ValueError("Invalid view type provided")

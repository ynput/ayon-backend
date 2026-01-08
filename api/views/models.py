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


class GenericViewModel(BaseViewModel):
    """Reports view model."""

    view_type: str
    settings: dict[str, Any]


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

    view_type: Literal["overview"] = "overview"
    settings: OverviewSettings


class TaskProgressViewPostModel(BaseViewPostModel):
    """Task progress view post model."""

    view_type: Literal["taskProgress"] = "taskProgress"
    settings: TaskProgressSettings


class ListsViewPostModel(BaseViewPostModel):
    """Lists view post model."""

    view_type: Literal["lists"] = "lists"
    settings: ListsSettings


class ReviewsViewPostModel(BaseViewPostModel):
    """Reviews view post model."""

    view_type: Literal["reviews"] = "reviews"
    settings: ReviewsSettings


class VersionsViewPostModel(BaseViewPostModel):
    """Versions view post model."""

    view_type: Literal["versions"] = "versions"
    settings: VersionsSettings


class GenericViewPostModel(BaseViewPostModel):
    view_type: str
    settings: dict[str, Any]


#
# Patch REST API models
#


class BaseViewPatchModel(OPModel):
    label: FViewLabel | None = None
    owner: FViewOwner | None = None
    settings: ViewSettingsModel | None = None


class OverviewViewPatchModel(BaseViewPatchModel):
    """Overview view post model."""

    view_type: Literal["overview"] = "overview"
    settings: OverviewSettings | None = None


class TaskProgressViewPatchModel(BaseViewPatchModel):
    """Task progress view post model."""

    view_type: Literal["taskProgress"] = "taskProgress"
    settings: TaskProgressSettings | None = None


class ListsViewPatchModel(BaseViewPatchModel):
    """Lists view post model."""

    view_type: Literal["lists"] = "lists"
    settings: ListsSettings | None = None


class ReviewsViewPatchModel(BaseViewPatchModel):
    """Reviews view post model."""

    view_type: Literal["reviews"] = "reviews"
    settings: ReviewsSettings | None = None


class VersionsViewPatchModel(BaseViewPatchModel):
    """Versions view post model."""

    view_type: Literal["versions"] = "versions"
    settings: VersionsSettings | None = None


class GenericViewPatchModel(BaseViewPatchModel):
    """Reports view post model."""

    view_type: str
    settings: dict[str, Any] | None = None


#
# Compound models
#


ViewModel = Annotated[
    OverviewViewModel
    | TaskProgressViewModel
    | ListsViewModel
    | ReviewsViewModel
    | VersionsViewModel
    | GenericViewModel,
    Field(
        discriminator="view_type",
        title="View model",
    ),
]

ViewPostModel = Annotated[
    OverviewViewPostModel
    | TaskProgressViewPostModel
    | ListsViewPostModel
    | ReviewsViewPostModel
    | VersionsViewPostModel
    | GenericViewPostModel,
    Field(
        discriminator="view_type",
        title="View post model",
    ),
]

ViewPatchModel = Annotated[
    OverviewViewPatchModel
    | TaskProgressViewPatchModel
    | ListsViewPatchModel
    | ReviewsViewPatchModel
    | VersionsViewPatchModel
    | GenericViewPatchModel,
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
    elif data.get("view_type") == "lists":
        return ListsViewModel(**data)
    elif data.get("view_type") == "reviews":
        return ReviewsViewModel(**data)
    elif data.get("view_type") == "versions":
        return VersionsViewModel(**data)
    else:
        return GenericViewModel(**data)


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
    else:
        return GenericViewPostModel


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
    else:
        return GenericViewPatchModel

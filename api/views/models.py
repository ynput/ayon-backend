from typing import Annotated, Any

from pydantic import Field

from ayon_server.types import OPModel
from ayon_server.utils import camelize
from ayon_server.views.models import (
    FViewId,
    FViewLabel,
    FViewOwner,
    FViewScope,
    FViewVisibility,
    FViewWorking,
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


class GenericViewModel(ViewListItemModel):
    """Reports view model."""

    view_type: str
    settings: dict[str, Any]
    access: dict[str, Any]


#
# POST REST API models
#


class GenericViewPostModel(OPModel):
    id: FViewId
    label: FViewLabel
    working: FViewWorking = True
    view_type: str | None = None
    settings: dict[str, Any]


#
# Patch REST API models
#


class GenericViewPatchModel(OPModel):
    """Reports view post model."""

    label: FViewLabel | None = None
    owner: FViewOwner | None = None

    view_type: str | None = None
    settings: dict[str, Any] | None = None


#
# Compound models
#


ViewModel = Annotated[
    GenericViewModel,
    Field(
        discriminator="view_type",
        title="View model",
    ),
]

ViewPostModel = GenericViewPostModel

ViewPatchModel = GenericViewPatchModel


def construct_view_model(**data: Any) -> ViewModel:
    """Temporary patching of stored views in typed format.

    Introduced by PR #974 TODO remove in next release.
    """
    view_type = data["view_type"]
    settings = data["settings"]
    if view_type in ["overview", "taskProgress", "lists", "reviews", "versions"]:
        patched_settings = {}
        for key, val in settings.items():
            if "_" in key:
                patched_settings[camelize(key)] = val
            else:
                patched_settings[key] = val
        data["settings"] = patched_settings
    return GenericViewModel(**data)


def get_post_model_class() -> type[ViewPostModel]:
    return GenericViewPostModel


def get_patch_model_class() -> type[ViewPatchModel]:
    return GenericViewPatchModel


def row_to_list_item(row: dict[str, Any], access_level: int) -> ViewListItemModel:
    """Convert a database row to a ViewListItemModel."""
    return ViewListItemModel(
        id=row["id"],
        scope=row["scope"],
        label=row["label"],
        position=row.get("position", 0),
        owner=row["owner"],
        visibility=row.get("visibility", "private"),
        working=row.get("working", False),
        access_level=access_level,
    )


def row_to_model(row: dict[str, Any], access_level: int) -> ViewModel:
    """Convert a database row to a ViewModel."""
    return construct_view_model(
        id=row["id"],
        view_type=row["view_type"],
        scope=row["scope"],
        label=row["label"],
        position=row.get("position", 0),
        owner=row["owner"],
        visibility=row.get("visibility", "private"),
        access=row.get("access", {}),
        working=row.get("working", False),
        settings=row.get("data", {}),
        access_level=access_level,
    )

"""Action manifest contains the metadata of an action.

The metadata includes the label, position, order, icon, addon name, and addon version.
This is all the information needed to display the action in the frontend.
"""

from typing import Literal

from ayon_server.types import Field, OPModel


class IconModel(OPModel):
    type: Literal["material-symbols", "url"] = Field("url")
    name: str | None = Field(
        None, description="The name of the icon (for material-symbols)"
    )
    color: str | None = Field(
        None, description="The color of the icon (for material-symbols)"
    )
    url: str | None = Field(None, description="The URL of the icon (for url)")


class BaseActionManifest(OPModel):
    identifier: str = Field(
        ...,
        description="The identifier of the action",
        example="maya.launch",
    )

    label: str = Field(
        ...,
        title="Label",
        description="Human-friendly name of the action",
        example="Launch Maya",
    )
    category: str = Field(
        "General",
        title="Category",
        description="Action category",
        example="Launch",
    )
    order: int = Field(
        100,
        title="Order",
        description="The order of the action",
        example=100,
    )
    icon: IconModel | None = Field(
        None,
        description="Path to the action icon",
        example={"type": "material-symbols", "name": "launch"},
    )

    # auto-populated by endpoints based on user preferences

    featured: bool = Field(False)

    # Addon name and addon version are auto-populated by the server

    addon_name: str | None = Field(
        None,
        title="Addon Name",
        description="The name of the addon providing the action",
        example="maya",
    )
    addon_version: str | None = Field(
        None,
        title="Addon Version",
        description="The version of the addon providing the action",
        example="1.5.6",
    )

    variant: str | None = Field(
        None,
        description="The settings variant of the addon",
        example="production",
    )


class SimpleActionManifest(BaseActionManifest):
    _action_type = "simple"

    entity_type: str | None = Field(
        None,
        title="Entity Type",
        description="The type of the entity",
        example="folder",
    )
    entity_subtypes: list[str] | None = Field(
        default_factory=list,
        title="Entity Subtypes",
        description="The subtype of the entity (folder type, task type)",
        example=["asset"],
    )
    allow_multiselection: bool = Field(
        False,
        title="Allow Multiselection",
        description="Allow multiple entities to be selected",
    )


class DynamicActionManifest(BaseActionManifest):
    _action_type = "dynamic"

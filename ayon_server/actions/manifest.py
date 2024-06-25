"""Action manifest contains the metadata of an action.

The metadata includes the label, position, order, icon, addon name, and addon version.
This is all the information needed to display the action in the frontend.
"""

from ayon_server.types import Field, OPModel


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
    position: list[str] | None = Field(
        None,
        title="Position",
        description="path to the action within tree/context menu",
        example=["DCC", "Launch"],
    )
    order: int = Field(
        100,
        title="Order",
        description="The order of the action",
        example=100,
    )
    icon: str | None = Field(
        None,
        description="The icon of the action. TBD",
        icon="maya",
    )

    # auto-populated by endpoints based on user preferences

    pinned: bool = Field(False, description="Whether the action is pinned")

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

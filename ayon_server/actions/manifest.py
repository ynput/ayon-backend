"""Action manifest contains the metadata of an action.

The metadata includes the label, position, order, icon, addon name, and addon version.
This is all the information needed to display the action in the frontend.



"""

from typing import Any, Literal

from ayon_server.types import Field, OPModel


class ActionTemplate(OPModel):
    """

    launcher:
    action returns ayon-uri which the frontend uses to open the launcher.

    """

    type: Literal["launcher", "http"] = Field(
        ...,
        title="Template type",
        description="The type of the template",
        example="http",
    )
    url: str | None = Field(
        None,
        description="The url to open in the browser",
        example="https:",
    )
    method: Literal["GET", "POST"] = Field(
        "GET",
        description="The method of the request",
    )
    payload: dict[str, Any] | None = Field(
        None,
        description="The payload of the request",
    )


class BaseActionManifest(OPModel):
    identifier: str = Field(
        ...,
        description="The identifier of the action",
    )

    label: str = Field(
        ...,
        title="Label",
        description="Human-friendly name of the action",
    )
    position: list[str] | None = Field(
        None,
        title="Position",
        description="path to the action within tree/context menu",
    )
    order: int = Field(
        100,
        title="Order",
        description="The order of the action",
    )
    icon: str | None = Field(
        None,
        description="The icon of the action. TBD",
    )

    # Addon name and addon version are auto-populated by the server

    addon_name: str | None = Field(
        None,
        title="Addon Name",
        description="The name of the addon providing the action",
    )
    addon_version: str | None = Field(
        None,
        title="Addon Version",
        description="The version of the addon providing the action",
    )

    variant: str | None = Field(None, description="The variant of the addon")


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
        example=["shot"],
    )
    allow_multiselection: bool = Field(
        False,
        title="Allow Multiselection",
        description="Allow multiple entities to be selected",
    )


class DynamicActionManifest(BaseActionManifest):
    _action_type = "dynamic"

"""Action manifest contains the metadata of an action.

The metadata includes the label, position, order, icon, addon name, and addon version.
This is all the information needed to display the action in the frontend.
"""

from typing import Annotated, Any, Literal

from ayon_server.types import Field, OPModel

IconType = Literal["material-symbols", "url"]


class IconModel(OPModel):
    type: Annotated[
        IconType,
        Field(
            title="Icon Type",
            example="material-symbols",
        ),
    ] = "url"

    name: Annotated[
        str | None,
        Field(
            title="Icon Name",
            description="The name of the icon (for type material-symbols)",
            example="icon_of_sin",
        ),
    ] = None

    color: Annotated[
        str | None,
        Field(
            title="Icon Color",
            description="The color of the icon (for type material-symbols)",
            example="#FF0000",
        ),
    ] = None

    url: Annotated[
        str | None,
        Field(
            description="The URL of the icon (for type url)",
            example="https://example.com/icon.png",
        ),
    ] = None


class BaseActionManifest(OPModel):
    identifier: Annotated[
        str,
        Field(
            title="Identifier",
            description="The identifier of the action",
            example="application.launch.adsk_3dsmax/2024",
        ),
    ]

    label: Annotated[
        str,
        Field(
            title="Label",
            description="Human-friendly name of the action",
            example="3ds Max 2024",
        ),
    ]

    group_label: Annotated[
        str | None,
        Field(
            title="Group Label",
            description="The label of the group the action belongs to",
            example="3ds Max",
        ),
    ] = None

    category: Annotated[
        str,
        Field(
            title="Category",
            description="Action category",
            example="Applications",
        ),
    ] = "General"

    order: Annotated[
        int,
        Field(
            title="Order",
            description="The order of the action",
            example=100,
        ),
    ] = 100

    icon: Annotated[
        IconModel | None,
        Field(
            title="Icon",
            description="An icon for the action",
            example={"type": "material-symbols", "name": "launch"},
        ),
    ] = None

    config_fields: list[dict[str, Any]] | None = None

    # auto-populated by endpoints based on user preferences

    featured: Annotated[
        bool,
        Field(
            title="Featured action",
            description="Sort icon to the top",
        ),
    ] = False

    # Addon name and addon version are auto-populated by the server

    addon_name: Annotated[
        str | None,
        Field(
            title="Addon Name",
            description="The name of the addon providing the action",
            example="applications",
        ),
    ] = None

    addon_version: Annotated[
        str | None,
        Field(
            title="Addon Version",
            description="The version of the addon providing the action",
            example="1.2.3",
        ),
    ] = None

    variant: Annotated[
        str | None,
        Field(
            title="Variant",
            description="The settings variant of the addon",
            example="production",
        ),
    ] = None


class SimpleActionManifest(BaseActionManifest):
    _action_type = "simple"

    entity_type: Annotated[
        str | None,
        Field(
            title="Entity Type",
            description="The type of the entity",
            example="folder",
        ),
    ] = None

    entity_subtypes: Annotated[
        list[str] | None,
        Field(
            title="Entity Subtypes",
            description="The subtype of the entity (folder type, task type)",
            example=["asset"],
        ),
    ] = None

    allow_multiselection: Annotated[
        bool,
        Field(
            title="Allow Multiselection",
            description="Allow multiple entities to be selected",
        ),
    ] = False


class DynamicActionManifest(BaseActionManifest):
    _action_type = "dynamic"

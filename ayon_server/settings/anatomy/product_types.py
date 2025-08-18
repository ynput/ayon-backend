from typing import Annotated

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class ProductTypeOverride(BaseSettingsModel):
    """Product type customization settings."""

    _layout = "compact"

    name: Annotated[str, SettingsField(title="Name")] = ""
    color: Annotated[str, SettingsField(title="Color", widget="color")] = "#cccccc"
    icon: Annotated[str, SettingsField(title="Icon", widget="icon")] = "deployed_code"


default_product_types = [
    ProductTypeOverride(name="image", icon="imagesmode"),
    ProductTypeOverride(name="render", icon="photo_library"),
    ProductTypeOverride(name="review", icon="photo_library"),
    ProductTypeOverride(name="plate", icon="camera_roll"),
    ProductTypeOverride(name="camera", icon="videocam"),
    ProductTypeOverride(name="model", icon="language"),
    ProductTypeOverride(name="texture", icon="texture"),
    ProductTypeOverride(name="look", icon="ev_shadow"),
    ProductTypeOverride(name="rig", icon="accessibility"),
    ProductTypeOverride(name="animation", icon="directions_run"),
    ProductTypeOverride(name="cache", icon="animation"),
    ProductTypeOverride(name="layout", icon="nature_people"),
    ProductTypeOverride(name="setdress", icon="forest"),
    ProductTypeOverride(name="groom", icon="content_cut"),
    ProductTypeOverride(name="matchmove", icon="switch_video"),
    ProductTypeOverride(name="vdbcache", icon="local_fire_department"),
    ProductTypeOverride(name="lightrig", icon="wb_incandescent"),
    ProductTypeOverride(name="lut", icon="opacity"),
    ProductTypeOverride(name="workfile", icon="home_repair_service"),
]


class DefaultProductType(BaseSettingsModel):
    color: Annotated[
        str,
        SettingsField(
            title="Default color",
            widget="color",
        ),
    ] = "#cccccc"

    icon: Annotated[
        str,
        SettingsField(
            title="Default icon",
            widget="icon",
        ),
    ] = "deployed_code"


# class ProductBaseType(BaseSettingsModel):
#     name: Annotated[str, SettingsField(title="Product Base Type")] = ""
#     color: Annotated[str, SettingsField(title="Color", widget="color")] = "#cccccc"
#     icon: Annotated[str, SettingsField(title="Icon", widget="icon")] = "deployed_code"
#     product_types: Annotated[
#         list[ProductTypeOverride],
#         SettingsField(default_factory=list, title="Product Types"),
#     ]
#
#


class ProductTypes(BaseSettingsModel):
    """Product types customization settings."""

    default: Annotated[
        DefaultProductType,
        SettingsField(
            title="Default appearance",
            description="Default appearance for product types",
        ),
    ] = DefaultProductType()

    definitions: Annotated[
        list[ProductTypeOverride],
        SettingsField(
            title="Appearance overrides",
            default_factory=lambda: default_product_types,
        ),
    ]


#   base_definitions: Annotated[
#         list[ProductBaseType],
#         SettingsField(
#             title="Product Base Types",
#             description="Product base types configuration",
#             default_factory=list,
#         ),
#     ]

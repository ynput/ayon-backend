from typing import Annotated

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class ProductTypeOverride(BaseSettingsModel):
    """Product type customization settings."""

    _layout = "compact"

    name: Annotated[str, SettingsField(title="Name")] = ""
    color: Annotated[str, SettingsField(title="Color", widget="color")] = "#cccccc"
    icon: Annotated[str, SettingsField(title="Icon", widget="icon")] = "deployed_code"


class ProductBaseType(BaseSettingsModel):
    name: Annotated[str, SettingsField(title="Product Base Type")] = ""
    color: Annotated[str, SettingsField(title="Color", widget="color")] = "#cccccc"
    icon: Annotated[str, SettingsField(title="Icon", widget="icon")] = "deployed_code"
    product_types: Annotated[
        list[ProductTypeOverride],
        SettingsField(default_factory=list, title="Product Types"),
    ]


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


class ProductTypes(BaseSettingsModel):
    """Product types customization settings."""

    default: Annotated[
        list[ProductTypeOverride],
        SettingsField(
            title="Default product types",
            default_factory=lambda: default_product_types,
        ),
    ]

    # TODO: For furture use, once base product types are implemented
    # base: Annotated[
    #     list[ProductBaseType],
    #     SettingsField(
    #         default_factory=list,
    #         title="Base product types",
    #     ),
    # ]

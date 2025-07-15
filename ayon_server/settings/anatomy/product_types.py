from typing import Annotated

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class ProductType(BaseSettingsModel):
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
        list[ProductType],
        SettingsField(default_factory=list, title="Product Types"),
    ]


default_product_types = [
    ProductType(name="image", icon="imagesmode"),
    ProductType(name="render", icon="photo_library"),
    ProductType(name="review", icon="photo_library"),
    ProductType(name="plate", icon="camera_roll"),
    ProductType(name="camera", icon="videocam"),
    ProductType(name="model", icon="language"),
    ProductType(name="texture", icon="texture"),
    ProductType(name="look", icon="ev_shadow"),
    ProductType(name="rig", icon="accessibility"),
    ProductType(name="animation", icon="directions_run"),
    ProductType(name="cache", icon="animation"),
    ProductType(name="layout", icon="nature_people"),
    ProductType(name="setdress", icon="forest"),
    ProductType(name="groom", icon="content_cut"),
    ProductType(name="matchmove", icon="switch_video"),
    ProductType(name="vdbcache", icon="local_fire_department"),
    ProductType(name="lightrig", icon="wb_incandescent"),
    ProductType(name="lut", icon="opacity"),
    ProductType(name="workfile", icon="home_repair_service"),
]


class ProductTypes(BaseSettingsModel):
    """Product types customization settings."""

    default: Annotated[
        list[ProductType],
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

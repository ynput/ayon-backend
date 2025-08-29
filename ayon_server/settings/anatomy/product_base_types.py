from typing import Annotated

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class ProductBaseType(BaseSettingsModel):
    """Product type customization settings."""

    _layout = "compact"

    name: Annotated[str, SettingsField(title="Name")] = ""
    color: Annotated[str, SettingsField(title="Color", widget="color")] = "#cccccc"
    icon: Annotated[str, SettingsField(title="Icon", widget="icon")] = "deployed_code"


default_product_type_definitions = [
    ProductBaseType(name="image", icon="imagesmode"),
    ProductBaseType(name="render", icon="photo_library"),
    ProductBaseType(name="review", icon="photo_library"),
    ProductBaseType(name="plate", icon="camera_roll"),
    ProductBaseType(name="camera", icon="videocam"),
    ProductBaseType(name="model", icon="language"),
    ProductBaseType(name="texture", icon="texture"),
    ProductBaseType(name="look", icon="ev_shadow"),
    ProductBaseType(name="rig", icon="accessibility"),
    ProductBaseType(name="animation", icon="directions_run"),
    ProductBaseType(name="cache", icon="animation"),
    ProductBaseType(name="layout", icon="nature_people"),
    ProductBaseType(name="setdress", icon="forest"),
    ProductBaseType(name="groom", icon="content_cut"),
    ProductBaseType(name="matchmove", icon="switch_video"),
    ProductBaseType(name="vdbcache", icon="local_fire_department"),
    ProductBaseType(name="lightrig", icon="wb_incandescent"),
    ProductBaseType(name="lut", icon="opacity"),
    ProductBaseType(name="workfile", icon="home_repair_service"),
]


class DefaultProductBaseType(BaseSettingsModel):
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


class ProductBaseTypes(BaseSettingsModel):
    """Product types customization settings."""

    default: Annotated[
        DefaultProductBaseType,
        SettingsField(
            title="Default appearance",
            description="Default appearance for product types",
        ),
    ] = DefaultProductBaseType()

    definitions: Annotated[
        list[ProductBaseType],
        SettingsField(
            title="Appearance overrides",
            default_factory=lambda: default_product_type_definitions,
        ),
    ]

from typing import Annotated

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class ProductBaseTypeOverride(BaseSettingsModel):
    """Product type customization settings."""

    _layout = "compact"

    name: Annotated[str, SettingsField(title="Name")] = ""
    color: Annotated[str, SettingsField(title="Color", widget="color")] = "#cccccc"
    icon: Annotated[str, SettingsField(title="Icon", widget="icon")] = "deployed_code"


default_product_type_definitions = [
    ProductBaseTypeOverride(name="image", icon="imagesmode"),
    ProductBaseTypeOverride(name="render", icon="photo_library"),
    ProductBaseTypeOverride(name="review", icon="photo_library"),
    ProductBaseTypeOverride(name="plate", icon="camera_roll"),
    ProductBaseTypeOverride(name="camera", icon="videocam"),
    ProductBaseTypeOverride(name="model", icon="language"),
    ProductBaseTypeOverride(name="texture", icon="texture"),
    ProductBaseTypeOverride(name="look", icon="ev_shadow"),
    ProductBaseTypeOverride(name="rig", icon="accessibility"),
    ProductBaseTypeOverride(name="animation", icon="directions_run"),
    ProductBaseTypeOverride(name="cache", icon="animation"),
    ProductBaseTypeOverride(name="layout", icon="nature_people"),
    ProductBaseTypeOverride(name="setdress", icon="forest"),
    ProductBaseTypeOverride(name="groom", icon="content_cut"),
    ProductBaseTypeOverride(name="matchmove", icon="switch_video"),
    ProductBaseTypeOverride(name="vdbcache", icon="local_fire_department"),
    ProductBaseTypeOverride(name="lightrig", icon="wb_incandescent"),
    ProductBaseTypeOverride(name="lut", icon="opacity"),
    ProductBaseTypeOverride(name="workfile", icon="home_repair_service"),
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
        list[ProductBaseTypeOverride],
        SettingsField(
            title="Appearance overrides",
            default_factory=lambda: default_product_type_definitions,
        ),
    ]

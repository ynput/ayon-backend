from typing import Annotated

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class ProductType(BaseSettingsModel):
    """Product type customization settings."""

    _layout = "compact"
    product_type: Annotated[str, SettingsField(title="Product Type")] = ""
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


class ProductTypes(BaseSettingsModel):
    """Product types customization settings."""

    defaults: Annotated[
        list[ProductType],
        SettingsField(default_factory=list, title="Defaults"),
    ]

    product_base_types: Annotated[
        list[ProductBaseType],
        SettingsField(default_factory=list, title="Base Types"),
    ]

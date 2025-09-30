from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


def get_separator_enum():
    return [
        {"value": "", "label": "None"},
        {"value": "_", "label": "Underscore (_)"},
        {"value": "-", "label": "Dash (-)"},
    ]


def get_case_enum():
    return [
        {"value": "lower", "label": "convert to lowercase"},
        {"value": "upper", "label": "CONVERT TO UPPERCASE"},
        {"value": "keep", "label": "Keep original case"},
        {"value": "capitalize", "label": "Capitalize First Letter"},
    ]


class EntityNaming(BaseSettingsModel):
    capitalization: str = SettingsField(
        "lower",
        title="Capitalization",
        enum_resolver=get_case_enum,
        description="How to capitalize the entity names",
    )
    separator: str = SettingsField(
        "_",
        title="Separator",
        enum_resolver=get_separator_enum,
        description="Character to separate different parts of the name",
    )

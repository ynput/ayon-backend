from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


def get_separator_enum():
    return [
        {"value": "", "label": "None"},
        {"value": "_", "label": "Underscore (_)"},
        {"value": "-", "label": "Dash (-)"},
        {"value": ".", "label": "Dot (.)"},
    ]


def get_case_enum():
    return [
        {"value": "lower", "label": "All lowercase"},
        {"value": "upper", "label": "All UPPERCASE"},
        {"value": "keep", "label": "Keep original capitalization"},
        {"value": "pascal", "label": "Capitalize Every Word"},
        {"value": "camel", "label": "capitalize Every Word Except First"},
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

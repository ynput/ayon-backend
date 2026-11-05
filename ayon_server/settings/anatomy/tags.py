from ayon_server.settings.settings_field import SettingsField

from .aux_model import BaseAuxModel


class Tag(BaseAuxModel):
    color: str = SettingsField(
        "#cacaca", title="Color", widget="color", example="#3498db"
    )
    colorLight: str | None = SettingsField(
        None,
        title="Light theme",
        widget="color",
        description="Leave empty to use the color on the light theme too.",
    )


default_tags = [
    Tag(name="important", color="#ff2450"),
    Tag(name="for reel", color="#5be1c6"),
]

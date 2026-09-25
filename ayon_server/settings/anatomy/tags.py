from ayon_server.settings.settings_field import SettingsField

from .aux_model import BaseAuxModel


class Tag(BaseAuxModel):
    color: str = SettingsField(
        "#cacaca", title="Color", widget="color", example="#3498db"
    )


default_tags = [
    Tag(name="important", color="#ff2450"),
    Tag(name="for reel", color="#5be1c6"),
]

from ayon_server.settings.settings_field import SettingsField
from ayon_server.types import OPModel


class ServerConfigModel(OPModel):
    instance_id: str | None = SettingsField(None, disabled=True)
    onboarding_finished: bool | None = SettingsField(None, disabled=True, scope=[])
    licenses: list[str] | None = SettingsField(None, disabled=True, scope=[])

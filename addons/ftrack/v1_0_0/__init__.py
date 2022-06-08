from openpype.addons import BaseServerAddonVersion

from .settings import FtrackSystemSettings


class AddOn(BaseServerAddonVersion):
    version = "1.0.0"
    system_settings = FtrackSystemSettings

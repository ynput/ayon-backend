from openpype.addons import BaseServerAddon

from .settings import FtrackSettings


class AddOn(BaseServerAddon):
    version = "1.1.0"
    settings = FtrackSettings

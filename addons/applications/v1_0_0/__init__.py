from openpype.addons import BaseServerAddonVersion

from .settings import ApplicationSettings


class AddOn(BaseServerAddonVersion):
    version = "1.0.0"
    settings = ApplicationSettings


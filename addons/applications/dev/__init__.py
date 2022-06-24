import json
import os

from openpype.addons import BaseServerAddon

from .settings import ApplicationSettings


class ApplicationsAddon(BaseServerAddon):
    name = "applications"
    version = "1.0.0"
    settings_model = ApplicationSettings

    async def get_default_settings(self):
        default_path = os.path.join(self.addon_dir, "applications.json")
        return self.get_settings_model()(**json.load(open(default_path)))

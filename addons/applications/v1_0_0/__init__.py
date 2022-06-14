import json
import os

from openpype.addons import BaseServerAddon

from .settings import ApplicationSettings


class AddOn(BaseServerAddon):
    version = "1.0.0"
    settings = ApplicationSettings

    async def get_default_settings(self):
        default_path = os.path.join(self.addon_dir, "applications.json")
        return self.settings(**json.load(open(default_path)))

import json
import os

from ayon_server.addons import BaseServerAddon

from .settings import ApplicationsAddonSettings


class ApplicationsAddon(BaseServerAddon):
    name = "applications"
    version = "1.0.0"
    settings_model = ApplicationsAddonSettings

    async def get_default_settings(self):
        applications_path = os.path.join(self.addon_dir, "applications.json")
        tools_path = os.path.join(self.addon_dir, "tools.json")
        default_values = {}
        with open(applications_path, "r") as stream:
            default_values.update(json.load(stream))

        with open(tools_path, "r") as stream:
            default_values.update(json.load(stream))

        return self.get_settings_model()(**default_values)

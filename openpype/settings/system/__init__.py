import functools
import json
import os

from openpype.settings.system.models import SystemSettings


@functools.cache
def get_default_system_settings() -> SystemSettings:
    """
    Return a Settings object with the default values.
    """
    base_dir = "openpype/settings/system/defaults"
    return SystemSettings(
        applications=json.load(open(os.path.join(base_dir, "applications.json"))),
        modules=json.load(open(os.path.join(base_dir, "modules.json"))),
        general={
            "artistCount": 1,
            "coffeeSize": "small",
            "milk": "none",
        },
    )

from pydantic import Field
from openpype.settings.common import BaseSettingsModel

from .common import AppGroupWithPython
from .maya import maya_defaults


class ApplicationSettings(BaseSettingsModel):
    """Applications settings"""

    maya: AppGroupWithPython = Field(default_factory=maya_defaults, title="Autodesk Maya")
    # flame: AppGroupWithPython = Field(..., title="Autodesk Flame")
    # nuke: AppGroupWithPython = Field(..., title="Nuke")
    # aftereffects: AppGroup = Field(..., title="Adobe After Effects")
    # photoshop: AppGroup = Field(..., title="Adobe Photoshop")
    # tvpaint: AppGroup = Field(..., title="TV Paint")
    # harmony: AppGroup = Field(..., title="Harmony")
    # additional_apps: AppGroup = Field(..., title="Additional Applications")


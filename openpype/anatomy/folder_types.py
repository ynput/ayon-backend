from openpype.settings.common import BaseSettingsModel
from pydantic import Field


class FolderType(BaseSettingsModel):
    _layout: str = "compact"
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    icon: str = Field("fa-folder", title="Icon")

    def __hash__(self):
        return hash(self.name)


default_folder_types = [
    FolderType(name="Library", icon="category"),
    FolderType(name="Episode", icon="live_tv"),
    FolderType(name="Asset", icon="smart_toy"),
    FolderType(name="Shot", icon="movie"),
    FolderType(name="Sequence", icon="theaters"),
]

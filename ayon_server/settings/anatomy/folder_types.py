from pydantic import validator

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class FolderType(BaseSettingsModel):
    _layout = "compact"
    name: str = SettingsField(..., title="Name", min_length=1, max_length=100)
    shortName: str = SettingsField("", title="Short name")
    icon: str = SettingsField("folder", title="Icon", widget="icon")

    # Set to old name when renaming
    original_name: str | None = SettingsField(None, title="Original name", scope=[])

    def __hash__(self):
        return hash(self.name)

    @validator("original_name")
    def validate_original_name(cls, v, values):
        if v is None:
            return values["name"]
        return v


default_folder_types = [
    FolderType(name="Folder", icon="folder"),
    FolderType(name="Library", shortName="lib", icon="category"),
    FolderType(name="Asset", icon="smart_toy"),
    FolderType(name="Episode", shortName="ep", icon="live_tv"),
    FolderType(name="Sequence", shortName="sq", icon="theaters"),
    FolderType(name="Shot", shortName="sh", icon="movie"),
]

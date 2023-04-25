from pydantic import Field, validator

from ayon_server.settings.common import BaseSettingsModel


class FolderType(BaseSettingsModel):
    _layout: str = "compact"
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    icon: str = Field("folder", title="Icon", widget="icon")
    original_name: str | None = Field(None, scope=[])  # Used for renaming

    def __hash__(self):
        return hash(self.name)

    @validator("original_name")
    def validate_original_name(cls, v, values):
        if v is None:
            return values["name"]
        return v


default_folder_types = [
    FolderType(name="Folder", icon="folder"),
    FolderType(name="Library", icon="category"),
    FolderType(name="Episode", icon="live_tv"),
    FolderType(name="Asset", icon="smart_toy"),
    FolderType(name="Shot", icon="movie"),
    FolderType(name="Sequence", icon="theaters"),
]

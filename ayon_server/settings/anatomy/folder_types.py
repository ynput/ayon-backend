from pydantic import Field, validator

from ayon_server.settings.common import BaseSettingsModel


class FolderType(BaseSettingsModel):
    _layout: str = "compact"
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    shortName: str = Field("", title="Short name")
    icon: str = Field("folder", title="Icon", widget="icon")

    # Set to old name when renaming
    original_name: str | None = Field(None, title="Original name", scope=[])

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

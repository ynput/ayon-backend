from ayon_server.settings.settings_field import SettingsField

from .aux_model import BaseAuxModel


class FolderType(BaseAuxModel):
    shortName: str = SettingsField("", title="Short name")
    color: str = SettingsField("#cccccc", title="Color", widget="color")
    icon: str = SettingsField("folder", title="Icon", widget="icon")


default_folder_types = [
    FolderType(name="Folder", icon="folder"),
    FolderType(name="Library", shortName="lib", icon="category"),
    FolderType(name="Asset", icon="smart_toy"),
    FolderType(name="Episode", shortName="ep", icon="live_tv"),
    FolderType(name="Sequence", shortName="sq", icon="theaters"),
    FolderType(name="Shot", shortName="sh", icon="movie"),
]

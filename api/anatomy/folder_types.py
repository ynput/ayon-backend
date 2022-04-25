from pydantic import BaseModel, Field


class FolderType(BaseModel):
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    icon: str = Field("fa-folder", title="Icon")

    def __hash__(self):
        return hash(self.name)


default_folder_types = [
    FolderType(name="Episode"),
    FolderType(name="Asset"),
    FolderType(name="Shot"),
    FolderType(name="Sequence"),
]

from datetime import datetime
from typing import Literal

from pydantic import validator

from ayon_server.types import Field, OPModel

SuggestionEntityType = Literal["task", "version", "user", "folder", "product"]


class SuggestionItem(OPModel):
    created_at: datetime | None = Field(
        None,
        title="Creation Date",
        description="The date and time when the suggested entity was created",
        example="2023-01-01T12:00:00Z",
    )
    relevance: float | None = Field(
        None,
        title="Relevance Score",
        description="The relevance score of the suggestion",
        example=0.85,
    )


class UserSuggestionItem(SuggestionItem):
    name: str = Field(..., example="john")
    full_name: str | None = Field(None, example="John Doe")


class FolderSuggestionItem(SuggestionItem):
    id: str = Field(..., example="af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b")
    folder_type: str = Field(..., example="Asset")
    name: str = Field(..., example="my_character")
    label: str | None = Field(None, example="My Character")
    thumbnail_id: str | None = Field(None)


class TaskSuggestionItem(SuggestionItem):
    id: str = Field(..., example="af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b")
    task_type: str = Field(..., example="Modeling")
    name: str = Field(..., example="modeling")
    label: str | None = Field(None)
    thumbnail_id: str | None = Field(None)
    parent: FolderSuggestionItem | None = Field(None)


class ProductSuggestionItem(SuggestionItem):
    id: str = Field(..., example="af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b")
    name: str = Field(..., example="model_main")
    product_type: str = Field(..., example="Model")
    parent: FolderSuggestionItem | None = Field(None)


class VersionSuggestionItem(SuggestionItem):
    id: str = Field(..., example="af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b")
    version: int = Field(..., example=1)
    parent: ProductSuggestionItem | None = Field(None)
    name: str | None = Field(None)

    @validator("name", pre=True, always=True)
    def set_name(cls, v, values):
        """Auto-populate the name field

        Sets the value of the 'name' field based
        on the input version number
        """

        if v:
            return v
        if values["version"] < 0:
            return "HERO"
        return f"v{values['version']:03d}"


SuggestionType = (
    UserSuggestionItem
    | TaskSuggestionItem
    | FolderSuggestionItem
    | VersionSuggestionItem
    | ProductSuggestionItem
)

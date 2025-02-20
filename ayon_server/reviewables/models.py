from datetime import datetime
from typing import Any

from ayon_server.helpers.ffprobe import ReviewableAvailability
from ayon_server.types import Field, OPModel


class ReviewableAuthor(OPModel):
    name: str = Field(..., title="Author Name")
    full_name: str | None = Field(None, title="Author Full Name")


class ReviewableProcessingStatus(OPModel):
    event_id: str | None = Field(None, title="Event ID")
    status: str = Field(..., title="Processing Status")
    description: str = Field(..., title="Processing Description")


class ReviewableModel(OPModel):
    file_id: str = Field(..., title="Reviewable ID")
    activity_id: str = Field(..., title="Activity ID")
    filename: str = Field(..., title="Reviewable Name")
    label: str | None = Field(None, title="Reviewable Label")
    mimetype: str = Field(..., title="Reviewable Mimetype")
    availability: ReviewableAvailability = Field(
        "unknown", title="Reviewable availability"
    )
    media_info: dict[str, Any] | None = Field(None, title="Media information")
    created_from: str | None = Field(None, title="File ID of the original file")
    processing: ReviewableProcessingStatus | None = Field(
        None,
        description="Information about the processing status",
    )
    created_at: datetime = Field(default_factory=datetime.now, title="Creation Date")
    updated_at: datetime = Field(default_factory=datetime.now, title="Update Date")
    author: ReviewableAuthor = Field(..., title="Author Information")

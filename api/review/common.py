from datetime import datetime
from typing import Any, Literal

from ayon_server.types import Field, OPModel

ReviewableAvailability = Literal["unknown", "needs_conversion", "ready"]


class ReviewableAuthor(OPModel):
    name: str = Field(..., title="Author Name")
    full_name: str | None = Field(None, title="Author Full Name")


class ReviewableProcessingStatus(OPModel):
    event_id: str = Field(..., title="Event ID")
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


class VersionReviewablesModel(OPModel):
    id: str = Field(
        ..., title="Version ID", example="1a3b34ce-1b2c-4d5e-6f7a-8b9c0d1e2f3a"
    )
    name: str = Field(..., title="Version Name", example="v001")
    version: str = Field(..., title="Version Number", example=1)
    status: str = Field(..., title="Version Status", example="In Review")

    reviewables: list[ReviewableModel] = Field(
        default_factory=list,
        title="Reviewables",
        description="List of available reviewables",
    )


COMPATIBILITY = {
    "codec": ["h264"],
    "pixelFormat": ["yuv420p"],
}


def availability_from_video_metadata(
    video_metadata: dict[str, Any],
) -> ReviewableAvailability:
    if not video_metadata:
        return "unknown"
    for key, values in COMPATIBILITY.items():
        if key not in video_metadata:
            return "unknown"
        if video_metadata[key] not in values:
            return "needs_conversion"
    return "ready"

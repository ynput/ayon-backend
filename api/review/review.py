from fastapi import Request

from ayon_server.api.dependencies import CurrentUser, ProjectName, VersionID

from .listing import ReviewableListModel
from .router import router
from .video import VideoResponse, serve_video


@router.get("")
async def list_version_reviewables(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
) -> ReviewableListModel:
    return ReviewableListModel(reviewables=[])


@router.get("/{reviewable_id}")
async def get_reviewable(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    reviewable_id: str,
) -> VideoResponse:
    return await serve_video(request, "/storage/server/pvw-placeholder.mp4")

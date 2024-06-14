from fastapi import Request

from ayon_server.api.dependencies import CurrentUser, ProjectName, VersionID
from ayon_server.exceptions import ForbiddenException

from .listing import ReviewableListModel
from .router import router
from .video import VideoResponse, get_reviewable_head, serve_video


@router.get("")
async def list_version_reviewables(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
) -> ReviewableListModel:
    return ReviewableListModel(reviewables=[])


@router.head("/{reviewable_id}")
async def head_reviewable(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    reviewable_id: str,
) -> VideoResponse:
    if not user.is_manager:
        accessGroups = user.data["accessGroups"]
        if project_name not in accessGroups:
            raise ForbiddenException(f"You don't have access to {project_name}")

    group = version_id[:2]
    root = f"/storage/server/projects/{project_name}/review"
    file_path = f"{root}/{group}/{version_id}/{reviewable_id}"

    return get_reviewable_head(request, file_path)


@router.get("/{reviewable_id}")
async def get_reviewable(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    reviewable_id: str,
) -> VideoResponse:
    if not user.is_manager:
        accessGroups = user.data["accessGroups"]
        if project_name not in accessGroups:
            raise ForbiddenException(f"You don't have access to {project_name}")

    group = version_id[:2]
    root = f"/storage/server/projects/{project_name}/review"
    file_path = f"{root}/{group}/{version_id}/{reviewable_id}"

    return await serve_video(request, file_path)

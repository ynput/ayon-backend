from fastapi import Response

from ayon_server.api.dependencies import CurrentUser, ProjectName, VersionID

from .router import router


@router.get("")
async def list_version_reviewables(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
):
    return {"message": "List of reviewables for a version"}


@router.get("/{reviewable_id}")
async def get_reviewable(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    reviewable_id: int,
):
    return Response(content="Reviewable content")

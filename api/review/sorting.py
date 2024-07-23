from ayon_server.api.dependencies import CurrentUser, ProjectName, VersionID
from ayon_server.types import OPModel

from .router import router


class SortReviewablesRequest(OPModel):
    ids: list[str]


@router.patch("/versions/{version_id}/reviewables")
async def sort_version_reviewables(
    user: CurrentUser, project_name: ProjectName, version_id: VersionID
) -> None:
    """Change the order of reviewables of a given version.

    In the payload, provide a list of activity ids (reviewables)
    in the order you want them to appear in the UI.
    """

    pass

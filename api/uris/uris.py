from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.exceptions import ForbiddenException
from ayon_server.types import Field, OPModel, ProjectLevelEntityType

from .router import router


class GetUrisRequest(OPModel):
    entity_type: ProjectLevelEntityType = Field(..., title="Entity type")
    ids: list[str] = Field(
        default_factory=list,
        title="Entity IDs",
    )


class UriResponseItem(OPModel):
    id: str = Field(..., title="Entity ID")
    uri: str = Field(..., title="Entity URI")


class GetUrisResponse(OPModel):
    uris: list[UriResponseItem] = Field(
        default_factory=list,
        title="List of URIs",
    )


@router.post("")
async def get_project_entity_uris(
    user: CurrentUser,
    project_name: ProjectName,
    request: GetUrisRequest,
) -> GetUrisResponse:
    """Return a list of Ayon URIs for the given entity IDs."""

    if not user.is_manager:
        if project_name not in user.data.get("accessGroups", {}):
            raise ForbiddenException("You do not have access to this project.")

    return GetUrisResponse(uris=[])

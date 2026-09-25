from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.exceptions import BadRequestException
from ayon_server.types import Field, OPModel, ProjectLevelEntityType

from .queries import (
    folder_uris,
    product_uris,
    representation_uris,
    task_uris,
    version_uris,
    workfile_uris,
)
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

    await user.ensure_project_access(project_name)

    if request.entity_type == "folder":
        uris = await folder_uris(project_name, request.ids)
    elif request.entity_type == "task":
        uris = await task_uris(project_name, request.ids)
    elif request.entity_type == "product":
        uris = await product_uris(project_name, request.ids)
    elif request.entity_type == "version":
        uris = await version_uris(project_name, request.ids)
    elif request.entity_type == "representation":
        uris = await representation_uris(project_name, request.ids)
    elif request.entity_type == "workfile":
        uris = await workfile_uris(project_name, request.ids)
    else:
        raise BadRequestException("Invalid entity type.")

    return GetUrisResponse(uris=[UriResponseItem(id=id, uri=uri) for id, uri in uris])

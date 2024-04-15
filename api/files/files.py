import os

from fastapi import Response
from starlette.responses import FileResponse

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.config import ayonconfig
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.types import Field, OPModel

from .router import router


def id_to_path(project_name: ProjectName, file_id: str) -> str:
    file_id = file_id.replace("-", "")
    assert len(file_id) == 32
    fgroup = file_id[:2]
    return os.path.join(
        ayonconfig.upload_dir,
        project_name,
        fgroup,
        file_id,
    )


class CreateFileResponseModel(OPModel):
    id: str = Field(..., example="123")


@router.post("", status_code=201)
async def upload_project_file(
    project_name: ProjectName,
    user: CurrentUser,
) -> CreateFileResponseModel:
    return CreateFileResponseModel(id="123")


@router.delete("/{file_id}")
async def delete_project_file(
    project_name: ProjectName,
    file_id: str,
    user: CurrentUser,
) -> EmptyResponse:
    return EmptyResponse()


@router.head("/{file_id}")
async def get_project_file_head(
    project_name: ProjectName,
    file_id: str,
    user: CurrentUser,
) -> EmptyResponse:
    return EmptyResponse()


@router.get("/{file_id}", response_model=None)
async def download_project_file(
    project_name: ProjectName,
    file_id: str,
    user: CurrentUser,
) -> FileResponse | Response:
    if not user.is_manager:
        if project_name not in user.data.get("accessGroups", {}):
            raise BadRequestException("User does not have access to the project")

    path = id_to_path(project_name, file_id)
    if not os.path.isfile(path):
        raise NotFoundException("File not found")

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=os.path.basename(path),
    )

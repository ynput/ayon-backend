from fastapi import Depends, Response
from projects.router import router

from openpype.api import ResponseFactory, dep_current_user
from openpype.entities import UserEntity
from openpype.exceptions import ForbiddenException
from openpype.helpers.deploy_project import create_project_from_anatomy
from openpype.settings.anatomy import Anatomy
from openpype.types import Field, OPModel


class DeployProjectRequestModel(OPModel):
    name: str = Field(..., description="Project name")
    code: str = Field(None, description="Project code")
    anatomy: Anatomy = Field(..., description="Project anatomy")
    library: bool = Field(False, description="Library project")


@router.post(
    "/projects",
    response_class=Response,
    status_code=201,
    responses={
        201: {"content": "", "description": "Project created"},
        409: ResponseFactory.error(409, "Project already exists"),
    },
)
async def deploy_project(
    payload: DeployProjectRequestModel,
    user: UserEntity = Depends(dep_current_user),
):
    """Create a new project using the provided anatomy object.

    Main purpose is to take an anatomy object and transform its contents
    to the project entity (along with additional data such as the project name).
    """

    if not user.is_manager:
        raise ForbiddenException("Only managers can create projects")

    await create_project_from_anatomy(
        name=payload.name,
        code=payload.code,
        anatomy=payload.anatomy,
        library=payload.library,
    )

    return Response(status_code=201)

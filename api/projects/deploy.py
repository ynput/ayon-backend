from typing import Annotated

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from ayon_server.helpers.deploy_project import (
    create_project_from_anatomy,
    create_project_skeleton_from_anatomy,
    promote_project_from_skeleton,
)
from ayon_server.helpers.project_list import get_project_info
from ayon_server.lib.postgres import Postgres
from ayon_server.settings.anatomy import Anatomy
from ayon_server.types import Field, OPModel

from .router import router


class DeployProjectRequestModel(OPModel):
    name: Annotated[
        str,
        Field(
            title="Project name",
            example="Example project",
        ),
    ]
    code: Annotated[
        str,
        Field(
            title="Project code",
        ),
    ]
    anatomy: Annotated[
        Anatomy | None,
        Field(
            title="Project anatomy",
        ),
    ] = None
    anatomy_preset: Annotated[
        str | None,
        Field(
            title="Anatomy preset name",
            description="Anatomy preset to use instead of providing anatomy",
        ),
    ] = None
    library: Annotated[
        bool,
        Field(
            title="Library project",
        ),
    ] = False
    assign_users: Annotated[
        bool,
        Field(title="Assign users", description="Assign default users to the project"),
    ] = True
    skeleton: Annotated[
        bool,
        Field(
            title="Create skeleton",
            description="Create a project skeleton instead of a full project",
        ),
    ] = False


@router.post("/projects", status_code=201)
async def deploy_project(
    payload: DeployProjectRequestModel,
    user: CurrentUser,
) -> None:
    """Create a new project using the provided anatomy object.

    Main purpose is to take an anatomy object and transform its contents
    to the project entity (along with additional data such as the project name).
    """

    user.check_permissions("studio.create_projects")

    try:
        existing_project = await get_project_info(
            payload.name,
            project_code=payload.code,
            with_skeleton=True,
        )
    except NotFoundException:
        pass

    else:
        msg = (
            f"Project {existing_project.name} ({existing_project.code}) already exists"
        )
        if existing_project.skeleton:
            msg += " as a skeleton."

            if not payload.skeleton:
                # promoting skeleton to full project.
                await promote_project_from_skeleton(
                    payload.name,
                    payload.anatomy,
                )
                return None

        raise ConflictException(msg)

    if payload.anatomy:
        anatomy = payload.anatomy
    elif payload.anatomy_preset:
        r = await Postgres.fetchrow(
            "SELECT data FROM anatomy_presets WHERE name = $1 AND version = $2",
            payload.anatomy_preset,
            "1.0.0",
        )
        if not r:
            raise NotFoundException(
                f"Anatomy preset {payload.anatomy_preset} not found"
            )
        anatomy = Anatomy(**r["data"])
    else:
        raise BadRequestException("Anatomy not provided")

    if payload.skeleton:
        await create_project_skeleton_from_anatomy(
            name=payload.name,
            code=payload.code,
            anatomy=anatomy,
            library=payload.library,
            user_name=user.name,
            assign_users=payload.assign_users,
        )
        return None

    await create_project_from_anatomy(
        name=payload.name,
        code=payload.code,
        anatomy=anatomy,
        library=payload.library,
        user_name=user.name,
        assign_users=payload.assign_users,
    )

    return None

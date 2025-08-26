from typing import Annotated

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.entities import ProjectEntity
from ayon_server.helpers.external_users import ExternalUsers, ExternalUserStatus
from ayon_server.types import Field, OPModel

from .router import router


class ExternalUserModel(OPModel):
    email: Annotated[
        str,
        Field(
            title="Email",
            example="foo.bar@example.com",
        ),
    ]

    full_name: Annotated[
        str | None,
        Field(
            title="Full name",
            example="Foo Bar",
        ),
    ] = None

    status: Annotated[
        ExternalUserStatus,
        Field(
            title="Status",
            example="pending",
        ),
    ] = "pending"


class ExternalUsersListModel(OPModel):
    users: Annotated[
        list[ExternalUserModel],
        Field(
            title="External users",
            default_factory=list,
        ),
    ]


@router.get("/projects/{project_name}/externalUsers")
async def list_external_users(
    user: CurrentUser, project_name: ProjectName
) -> ExternalUsersListModel:
    """Retrieve a project statistics by its name."""

    user.check_permissions("project.access", project_name)
    project = await ProjectEntity.load(name=project_name)
    external_users = project.data.get("externalUsers", {})
    emails = sorted(external_users.keys())
    result = []
    for email in emails:
        user_data = external_users[email]
        result.append(
            ExternalUserModel(
                email=email,
                full_name=user_data.get("fullName"),
                status=user_data.get("status", "pending"),
            )
        )
    return ExternalUsersListModel(users=result)


class AddExternalUserModel(OPModel):
    email: Annotated[str, Field(title="Email", example="foo.bar@example.com")]
    full_name: Annotated[str | None, Field(title="Full name", example="Foo Bar")] = None


@router.post("/projects/{project_name}/externalUsers")
async def add_external_user(
    user: CurrentUser,
    project_name: ProjectName,
    payload: AddExternalUserModel,
):
    user.check_permissions("project.access", project_name, write=True)

    await ExternalUsers.add(
        email=payload.email,
        project_name=project_name,
        full_name=payload.full_name,
    )


@router.delete("/projects/{project_name}/externalUsers/{email}")
async def remove_external_user(
    user: CurrentUser,
    project_name: ProjectName,
    email: str,
):
    user.check_permissions("project.access", project_name, write=True)

    await ExternalUsers.remove(email=email, project_name=project_name)

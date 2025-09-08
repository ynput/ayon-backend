from typing import Annotated

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.entities import ProjectEntity
from ayon_server.helpers.guest_users import GuestUsers, GuestUserStatus
from ayon_server.types import Field, OPModel

from .router import router


class GuestUserModel(OPModel):
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
        GuestUserStatus,
        Field(
            title="Status",
            example="pending",
        ),
    ] = "pending"


class GuestUsersListModel(OPModel):
    users: Annotated[
        list[GuestUserModel],
        Field(
            title="Guest users",
            default_factory=list,
        ),
    ]


@router.get("/projects/{project_name}/guests")
async def list_guest_users(
    user: CurrentUser, project_name: ProjectName
) -> GuestUsersListModel:
    """Retrieve a project statistics by its name."""

    user.check_permissions("project.access", project_name)
    project = await ProjectEntity.load(name=project_name)
    guest_users = project.data.get("guestUsers", {})
    emails = sorted(guest_users.keys())
    result = []
    for email in emails:
        user_data = guest_users[email]
        result.append(
            GuestUserModel(
                email=email,
                full_name=user_data.get("fullName"),
                status=user_data.get("status", "pending"),
            )
        )
    return GuestUsersListModel(users=result)


class AddGuestUserModel(OPModel):
    email: Annotated[str, Field(title="Email", example="foo.bar@example.com")]
    full_name: Annotated[str | None, Field(title="Full name", example="Foo Bar")] = None


@router.post("/projects/{project_name}/guests")
async def add_guest_user(
    user: CurrentUser,
    project_name: ProjectName,
    payload: AddGuestUserModel,
):
    user.check_permissions("project.access", project_name, write=True)

    await GuestUsers.add(
        email=payload.email,
        project_name=project_name,
        full_name=payload.full_name,
    )


@router.delete("/projects/{project_name}/guests/{email}")
async def remove_guest_user(
    user: CurrentUser,
    project_name: ProjectName,
    email: str,
):
    user.check_permissions("project.access", project_name, write=True)

    await GuestUsers.remove(email=email, project_name=project_name)

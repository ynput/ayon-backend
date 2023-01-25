import strawberry
from fastapi import Depends
from strawberry.dataloader import DataLoader
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from ayon_server.api.dependencies import dep_current_user
from ayon_server.entities import UserEntity
from ayon_server.graphql.connections import (
    EventsConnection,
    ProjectsConnection,
    UsersConnection,
)
from ayon_server.graphql.dataloaders import (
    folder_loader,
    latest_version_loader,
    subset_loader,
    task_loader,
    user_loader,
    version_loader,
    workfile_loader,
)
from ayon_server.graphql.nodes.folder import folder_from_record
from ayon_server.graphql.nodes.project import ProjectNode, project_from_record
from ayon_server.graphql.nodes.representation import representation_from_record
from ayon_server.graphql.nodes.subset import subset_from_record
from ayon_server.graphql.nodes.task import task_from_record
from ayon_server.graphql.nodes.user import UserAttribType, UserNode, user_from_record
from ayon_server.graphql.nodes.version import version_from_record
from ayon_server.graphql.nodes.workfile import workfile_from_record
from ayon_server.graphql.resolvers.events import get_events
from ayon_server.graphql.resolvers.links import get_links
from ayon_server.graphql.resolvers.projects import get_project, get_projects
from ayon_server.graphql.resolvers.users import get_user, get_users


async def graphql_get_context(user: UserEntity = Depends(dep_current_user)) -> dict:
    """Get the current request context"""
    return {
        # Auth
        "user": user,
        # Record parsing
        "folder_from_record": folder_from_record,
        "subset_from_record": subset_from_record,
        "version_from_record": version_from_record,
        "representation_from_record": representation_from_record,
        "task_from_record": task_from_record,
        "user_from_record": user_from_record,
        "project_from_record": project_from_record,
        "workfile_from_record": workfile_from_record,
        # Data loaders
        "folder_loader": DataLoader(load_fn=folder_loader),
        "subset_loader": DataLoader(load_fn=subset_loader),
        "task_loader": DataLoader(load_fn=task_loader),
        "version_loader": DataLoader(load_fn=version_loader),
        "latest_version_loader": DataLoader(load_fn=latest_version_loader),
        "user_loader": DataLoader(load_fn=user_loader),
        "workfile_loader": DataLoader(load_fn=workfile_loader),
        # Other
        "links_resolver": get_links,
    }


#
# Query
#


@strawberry.type
class Query:
    """Ayon GraphQL Query."""

    project: ProjectNode = strawberry.field(
        description="Get a project by name",
        resolver=get_project,
    )

    projects: ProjectsConnection = strawberry.field(
        description="Get a list of projects",
        resolver=get_projects,
    )

    users: UsersConnection = strawberry.field(
        description="Get a list of users",
        resolver=get_users,
    )

    user: UserNode = strawberry.field(
        description="Get a user by name",
        resolver=get_user,
    )

    events: EventsConnection = strawberry.field(
        description="Get a list of recorded events",
        resolver=get_events,
    )

    @strawberry.field(description="Current user")
    def me(self, info: Info) -> UserNode:
        user = info.context["user"]
        return UserNode(
            name=user.name,
            active=user.active,
            updated_at=user.updated_at,
            created_at=user.created_at,
            attrib=UserAttribType(**user.attrib.dict()),
            roles=user.data.get("roles", {}),
            is_admin=user.is_admin,
            is_manager=user.is_manager,
            is_service=user.is_service,
            is_guest=False,  # TODO
            default_roles=user.data.get("defaultRoles", []),
            has_password=bool(user.data.get("password")),
            apiKeyPreview=user.data.get("apiKeyPreview"),
        )


schema = strawberry.Schema(query=Query)
router = GraphQLRouter(
    schema=schema,
    graphiql=False,
    context_getter=graphql_get_context,
)

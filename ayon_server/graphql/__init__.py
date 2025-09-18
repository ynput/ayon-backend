import os
import traceback
from typing import Any

import strawberry
from graphql import GraphQLError
from strawberry.dataloader import DataLoader
from strawberry.fastapi import GraphQLRouter
from strawberry.types import ExecutionContext

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import AyonException
from ayon_server.graphql.connections import (
    ActivitiesConnection,
    EventsConnection,
    KanbanConnection,
    ProjectsConnection,
    UsersConnection,
)
from ayon_server.graphql.dataloaders import (
    folder_loader,
    latest_version_loader,
    product_loader,
    representation_loader,
    task_loader,
    user_loader,
    version_loader,
    workfile_loader,
)
from ayon_server.graphql.nodes.common import ProductType
from ayon_server.graphql.nodes.entity_list import entity_list_from_record
from ayon_server.graphql.nodes.folder import folder_from_record
from ayon_server.graphql.nodes.product import product_from_record
from ayon_server.graphql.nodes.project import ProjectNode, project_from_record
from ayon_server.graphql.nodes.representation import representation_from_record
from ayon_server.graphql.nodes.task import task_from_record
from ayon_server.graphql.nodes.user import UserNode, user_from_record
from ayon_server.graphql.nodes.version import version_from_record
from ayon_server.graphql.nodes.workfile import workfile_from_record
from ayon_server.graphql.resolvers.activities import get_activities
from ayon_server.graphql.resolvers.entity_list_items import get_entity_list_items
from ayon_server.graphql.resolvers.events import get_events
from ayon_server.graphql.resolvers.inbox import get_inbox
from ayon_server.graphql.resolvers.kanban import get_kanban
from ayon_server.graphql.resolvers.links import get_links
from ayon_server.graphql.resolvers.projects import get_project, get_projects
from ayon_server.graphql.resolvers.users import get_user, get_users
from ayon_server.graphql.types import Info
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.utils import json_dumps


async def graphql_get_context(user: CurrentUser) -> dict[str, Any]:
    """Get the current request context"""
    return {
        # Auth
        "user": user,
        # Record parsing
        "entity_list_from_record": entity_list_from_record,
        "folder_from_record": folder_from_record,
        "product_from_record": product_from_record,
        "version_from_record": version_from_record,
        "representation_from_record": representation_from_record,
        "task_from_record": task_from_record,
        "user_from_record": user_from_record,
        "project_from_record": project_from_record,
        "workfile_from_record": workfile_from_record,
        # Data loaders
        "folder_loader": DataLoader(load_fn=folder_loader),
        "product_loader": DataLoader(load_fn=product_loader),
        "task_loader": DataLoader(load_fn=task_loader),
        "version_loader": DataLoader(load_fn=version_loader),
        "latest_version_loader": DataLoader(load_fn=latest_version_loader),
        "user_loader": DataLoader(load_fn=user_loader),
        "workfile_loader": DataLoader(load_fn=workfile_loader),
        "representation_loader": DataLoader(load_fn=representation_loader),
        # Other
        "activities_resolver": get_activities,
        "links_resolver": get_links,
        "entity_list_items_resolver": get_entity_list_items,
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

    inbox: ActivitiesConnection = strawberry.field(
        description="Get user inbox",
        resolver=get_inbox,
    )

    kanban: KanbanConnection = strawberry.field(
        description="Get kanban board",
        resolver=get_kanban,
    )

    @strawberry.field(description="Current user")
    def me(self, info: Info) -> UserNode:
        user = info.context["user"]
        return UserNode(
            name=user.name,
            active=user.active,
            updated_at=user.updated_at,
            created_at=user.created_at,
            _attrib=user.attrib.dict(),
            access_groups=json_dumps(user.data.get("accessGroups", {})),
            is_admin=user.is_admin,
            is_manager=user.is_manager,
            is_service=user.is_service,
            is_developer=user.is_developer,
            is_guest=user.is_guest,
            user_pool=user.data.get("userPool"),
            default_access_groups=user.data.get("defaultAccessGroups", []),
            has_password=bool(user.data.get("password")),
            apiKeyPreview=user.data.get("apiKeyPreview"),
            _user=user,
        )

    @strawberry.field(description="Studio-wide product type configuration")
    async def product_types(self) -> list[ProductType]:
        return [
            ProductType(
                name=row["name"],
                icon=row["data"].get("icon"),
                color=row["data"].get("color"),
            )
            async for row in Postgres.iterate(
                """SELECT name, data FROM product_types
                ORDER BY name ASC"""
            )
        ]


class AyonSchema(strawberry.Schema):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def process_errors(
        self,
        errors: list[GraphQLError],
        execution_context: ExecutionContext | None = None,
    ) -> None:
        for error in errors:
            if isinstance(error.original_error, AyonException):
                error.extensions = {"status": error.original_error.status}
                status_code = error.original_error.status
                if status_code in [401, 403, 404]:
                    # Don't log operational errors
                    continue

            elif isinstance(error, GraphQLError) and error.original_error is None:
                message = error.message
                if error.locations:
                    line_no = error.locations[0]
                    location = f" at line {line_no.line}"
                logger.error(f"[GRAPHQL] {message}{location}")
                status_code = 400
                continue

            else:
                status_code = 500

            if error.original_error:
                # get the module and line number of the original error
                tb = traceback.extract_tb(error.original_error.__traceback__)
                if not tb:
                    continue
                fname, line_no, func, msg = tb[-1]

                fname = fname.replace(os.getcwd(), "")
                fname = fname.removeprefix("/ayon_server/")
                fname = fname.removesuffix(".py")
                fname = fname.replace("/", ".")

                if error.path:
                    path = "/".join([str(k) for k in error.path])
                else:
                    path = ""

                message = error.message.replace("{", "{{").replace("}", "}}")
                logger.error(
                    f"[GRAPHQL] Error resolving {path} (line {line_no}): {message}",
                    module=fname,
                )
                continue

            logger.error(
                f"[GRAPHQL] Unhandled '{error.__class__.__name__}' error: {error}"
            )


router: GraphQLRouter[Any, Any] = GraphQLRouter(
    schema=AyonSchema(query=Query),
    graphiql=False,
    context_getter=graphql_get_context,
)

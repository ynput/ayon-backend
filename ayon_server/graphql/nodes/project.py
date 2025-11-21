from datetime import datetime
from typing import TYPE_CHECKING, Any

import strawberry
from strawberry import LazyType

from ayon_server.entities import ProjectEntity
from ayon_server.entities.user import UserEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.graphql.connections import ActivitiesConnection, EntityListsConnection
from ayon_server.graphql.nodes.common import ProductBaseType, ProductType, ThumbnailInfo
from ayon_server.graphql.resolvers.activities import get_activities
from ayon_server.graphql.resolvers.entity_lists import get_entity_list, get_entity_lists
from ayon_server.graphql.resolvers.folders import get_folder, get_folders
from ayon_server.graphql.resolvers.products import get_product, get_products
from ayon_server.graphql.resolvers.representations import (
    get_representation,
    get_representations,
)
from ayon_server.graphql.resolvers.tasks import get_task, get_tasks
from ayon_server.graphql.resolvers.versions import get_version, get_versions
from ayon_server.graphql.resolvers.workfiles import get_workfile, get_workfiles
from ayon_server.graphql.utils import parse_attrib_data, process_attrib_data
from ayon_server.helpers.tags import get_used_project_tags
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import json_dumps

if TYPE_CHECKING:
    from ayon_server.graphql.connections import (
        EntityListsConnection,
        FoldersConnection,
        ProductsConnection,
        RepresentationsConnection,
        TasksConnection,
        VersionsConnection,
        WorkfilesConnection,
    )
    from ayon_server.graphql.nodes.entity_list import EntityListNode
    from ayon_server.graphql.nodes.folder import FolderNode
    from ayon_server.graphql.nodes.product import ProductNode
    from ayon_server.graphql.nodes.representation import RepresentationNode
    from ayon_server.graphql.nodes.task import TaskNode
    from ayon_server.graphql.nodes.version import VersionNode
    from ayon_server.graphql.nodes.workfile import WorkfileNode
else:
    EntityListConnection = LazyType["EntityListConnection", "..connections"]
    FoldersConnection = LazyType["FoldersConnection", "..connections"]
    RepresentationsConnection = LazyType["RepresentationsConnection", "..connections"]
    ProductsConnection = LazyType["ProductsConnection", "..connections"]
    TasksConnection = LazyType["TasksConnection", "..connections"]
    VersionsConnection = LazyType["VersionsConnection", "..connections"]
    WorkfilesConnection = LazyType["WorkfilesConnection", "..connections"]

    EntityListNode = LazyType["EntityListNode", ".entity_list"]
    FolderNode = LazyType["FolderNode", ".folder"]
    RepresentationNode = LazyType["RepresentationNode", ".representation"]
    ProductNode = LazyType["ProductNode", ".product"]
    TaskNode = LazyType["TaskNode", ".task"]
    VersionNode = LazyType["VersionNode", ".version"]
    WorkfileNode = LazyType["WorkfileNode", ".workfile"]


@strawberry.type
class TaskType:
    name: str
    icon: str | None = None
    short_name: str | None = None
    color: str | None = None


@strawberry.type
class FolderType:
    name: str
    icon: str | None = None
    short_name: str | None = None
    color: str | None = None


@strawberry.type
class LinkType:
    name: str
    link_type: str
    input_type: str
    output_type: str
    color: str | None = None
    style: str = "solid"


@strawberry.type
class Status:
    name: str
    short_name: str | None = None
    icon: str | None = None
    color: str | None = None
    state: str | None = None
    scope: list[str] | None = None


@strawberry.type
class Tag:
    name: str
    color: str | None = None


@strawberry.type
class ProjectBundleType:
    production: str | None = None
    staging: str | None = None


@ProjectEntity.strawberry_attrib()
class ProjectAttribType:
    pass


@strawberry.type
class ProjectNode:
    name: str = strawberry.field()
    project_name: str = strawberry.field()
    code: str = strawberry.field()
    data: str | None
    config: str | None
    active: bool
    library: bool
    thumbnail: ThumbnailInfo | None = None
    bundle: ProjectBundleType
    created_at: datetime
    updated_at: datetime

    _attrib: strawberry.Private[dict[str, Any]]
    _user: strawberry.Private[UserEntity]

    @strawberry.field
    def attrib(self) -> ProjectAttribType:
        return parse_attrib_data(
            "project",
            ProjectAttribType,
            self._attrib,
            user=self._user,
            project_name=self.project_name,
        )

    @strawberry.field
    def all_attrib(self) -> str:
        return json_dumps(
            process_attrib_data(
                "project",
                self._attrib,
                user=self._user,
                project_name=self.project_name,
            )
        )

    entity_list: EntityListNode = strawberry.field(
        resolver=get_entity_list,
        description=get_entity_list.__doc__,
    )

    entity_lists: EntityListsConnection = strawberry.field(
        resolver=get_entity_lists,
        description=get_entity_lists.__doc__,
    )

    folder: FolderNode | None = strawberry.field(
        resolver=get_folder,
        description=get_folder.__doc__,
    )

    folders: FoldersConnection = strawberry.field(
        resolver=get_folders,
        description=get_folders.__doc__,
    )

    task: TaskNode | None = strawberry.field(
        resolver=get_task,
        description=get_task.__doc__,
    )

    tasks: TasksConnection = strawberry.field(
        resolver=get_tasks,
        description=get_tasks.__doc__,
    )

    product: ProductNode | None = strawberry.field(
        resolver=get_product,
        description=get_product.__doc__,
    )

    products: ProductsConnection = strawberry.field(
        resolver=get_products,
        description=get_products.__doc__,
    )

    version: VersionNode | None = strawberry.field(
        resolver=get_version,
        description=get_version.__doc__,
    )

    versions: VersionsConnection = strawberry.field(
        resolver=get_versions,
        description=get_versions.__doc__,
    )

    representation: RepresentationNode | None = strawberry.field(
        resolver=get_representation,
        description=get_representation.__doc__,
    )

    representations: RepresentationsConnection = strawberry.field(
        resolver=get_representations,
        description=get_representations.__doc__,
    )

    workfile: WorkfileNode | None = strawberry.field(
        resolver=get_workfile,
        description=get_workfile.__doc__,
    )

    workfiles: WorkfilesConnection = strawberry.field(
        resolver=get_workfiles,
        description=get_workfiles.__doc__,
    )

    activities: ActivitiesConnection = strawberry.field(
        resolver=get_activities,
        description=get_activities.__doc__,
    )

    @strawberry.field(description="List of project's task types")
    async def task_types(self, active_only: bool = False) -> list[TaskType]:
        cond = ""
        if active_only:
            cond = f"""
                WHERE name IN (SELECT DISTINCT(task_type)
                FROM project_{self.project_name}.tasks)
            """
        query = f"""
            SELECT name, data
            FROM project_{self.project_name}.task_types
            {cond}
            ORDER BY position
        """
        res = await Postgres.fetch(query)
        return [
            TaskType(
                name=row["name"],
                short_name=row["data"].get("shortName"),
                icon=row["data"].get("icon"),
                color=row["data"].get("color"),
            )
            for row in res
        ]

    @strawberry.field(description="List of project's folder types")
    async def folder_types(self, active_only: bool = False) -> list[FolderType]:
        cond = ""
        if active_only:
            cond = f"""
                WHERE name IN (SELECT DISTINCT(folder_type)
                FROM project_{self.project_name}.folders)
            """

        query = f"""
            SELECT name, data
            FROM project_{self.project_name}.folder_types
            {cond}
            ORDER BY position
        """
        res = await Postgres.fetch(query)
        return [
            FolderType(
                name=row["name"],
                short_name=row["data"].get("shortName"),
                color=row["data"].get("color"),
                icon=row["data"].get("icon"),
            )
            for row in res
        ]

    @strawberry.field(description="List of project's link types")
    async def link_types(self, active_only: bool = False) -> list[LinkType]:
        cond = ""
        if active_only:
            cond = f"""
                WHERE name IN (SELECT DISTINCT(link_type)
                FROM project_{self.project_name}.links)
            """

        query = f"""
            SELECT name, link_type, input_type, output_type, data
            FROM project_{self.project_name}.link_types
            {cond}
            ORDER BY name
        """

        res = await Postgres.fetch(query)
        return [
            LinkType(
                name=row["name"],
                link_type=row["link_type"],
                input_type=row["input_type"],
                output_type=row["output_type"],
                color=row["data"].get("color"),
                style=row["data"].get("style", "solid"),
            )
            for row in res
        ]

    @strawberry.field(description="List of project's product types")
    async def product_types(self) -> list[ProductType]:
        return [
            ProductType(
                name=row["name"],
                icon=row["data"].get("icon"),
                color=row["data"].get("color"),
            )
            async for row in Postgres.iterate(
                f"""
                SELECT name, data FROM product_types
                WHERE name IN (
                    SELECT DISTINCT(product_type)
                    FROM project_{self.project_name}.products
                )
                ORDER BY name ASC
            """
            )
        ]

    @strawberry.field(description="List of project's product base types")
    async def product_base_types(self) -> list[ProductBaseType]:
        return [
            ProductBaseType(
                name=row["name"],
            )
            async for row in Postgres.iterate(
                f"""
                SELECT DISTINCT(product_base_type) AS name
                FROM project_{self.project_name}.products
                WHERE product_base_type IS NOT NULL
                ORDER BY name ASC
            """
            )
        ]

    @strawberry.field(description="List of project's statuses")
    async def statuses(self) -> list[Status]:
        query = f"""
            SELECT name, data
            FROM project_{self.project_name}.statuses
            ORDER BY position
        """
        res = await Postgres.fetch(query)
        return [
            Status(
                name=row["name"],
                short_name=row["data"].get("shortName"),
                icon=row["data"].get("icon"),
                color=row["data"].get("color"),
                state=row["data"].get("state"),
                scope=row["data"].get("scope", []),
            )
            for row in res
        ]

    @strawberry.field(description="List of tags in the project")
    async def tags(self) -> list[Tag]:
        query = f"""
            SELECT name, data
            FROM project_{self.project_name}.tags
            ORDER BY position
        """
        res = await Postgres.fetch(query)
        return [
            Tag(
                name=row["name"],
                color=row["data"].get("color"),
            )
            for row in res
        ]

    @strawberry.field(description="List of tags used in the project")
    async def used_tags(self) -> list[str]:
        return await get_used_project_tags(self.project_name)


async def project_from_record(
    project_name: str | None, record: dict[str, Any], context: dict[str, Any]
) -> ProjectNode:
    """Construct a project node from a DB row."""

    project_name = project_name or record["name"]
    assert project_name is not None, "Project name must not be None"

    thumbnail = None
    user = context["user"]
    if user.is_guest:
        guest_users = record.get("data", {}).get("guestUsers", {})
        if user.attrib.email not in guest_users:
            raise ForbiddenException("You do not have access to this project.")

        # guest users do not have access to project internal data
        data = {}
        config = None
        bundle = ProjectBundleType()
    else:
        user.check_project_access(record["name"])

        data = record.get("data", {})
        config = record.get("config", None)
        bundle_data = data.get("bundle", {})
        if bundle_data:
            bundle = ProjectBundleType(
                production=bundle_data.get("production", None),
                staging=bundle_data.get("staging", None),
            )
        else:
            bundle = ProjectBundleType()

    return ProjectNode(
        name=record["name"],
        code=record["code"],
        project_name=record["name"],
        active=record["active"],
        library=record["library"],
        thumbnail=thumbnail,
        data=json_dumps(data) if data else None,
        config=json_dumps(config) if config else None,
        bundle=bundle,
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        _user=context["user"],
        _attrib=record["attrib"],
    )


ProjectNode.from_record = staticmethod(project_from_record)  # type: ignore

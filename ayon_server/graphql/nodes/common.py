from datetime import datetime

import strawberry

from ayon_server.exceptions import AyonException
from ayon_server.graphql.connections import ActivitiesConnection
from ayon_server.graphql.types import BaseConnection, BaseEdge, Info
from ayon_server.logging import logger


@strawberry.type
class ProductType(BaseEdge):
    name: str = strawberry.field()
    icon: str | None = strawberry.field(default=None)
    color: str | None = strawberry.field(default=None)


@strawberry.type
class LinkEdge(BaseEdge):
    id: str = strawberry.field()
    project_name: str = strawberry.field()
    entity_type: str = strawberry.field()
    entity_id: str = strawberry.field()
    name: str | None = strawberry.field(default=None)
    link_type: str = strawberry.field(default="something")
    direction: str = strawberry.field(default="in")
    description: str = strawberry.field(default="")
    author: str | None = strawberry.field(default=None)
    cursor: str | None = strawberry.field(default=None)

    @strawberry.field(description="Linked node")
    async def node(self, info: Info) -> "BaseNode":
        if self.entity_type == "folder":
            loader = info.context["folder_loader"]
            parser = info.context["folder_from_record"]
        elif self.entity_type == "version":
            loader = info.context["version_loader"]
            parser = info.context["version_from_record"]
        elif self.entity_type == "product":
            loader = info.context["product_loader"]
            parser = info.context["product_from_record"]
        elif self.entity_type == "task":
            loader = info.context["task_loader"]
            parser = info.context["task_from_record"]
        elif self.entity_type == "representation":
            loader = info.context["representation_loader"]
            parser = info.context["representation_from_record"]
        elif self.entity_type == "workfile":
            loader = info.context["workfile_loader"]
            parser = info.context["workfile_from_record"]
        else:
            msg = f"Unsupported entity type '{self.entity_type}' for link node"
            logger.error(msg)
            raise AyonException(msg)

        record = await loader.load((self.project_name, self.entity_id))
        return await parser(self.project_name, record, info.context)


@strawberry.type
class LinksConnection(BaseConnection):
    edges: list[LinkEdge] = strawberry.field(default_factory=list)


@strawberry.type
class ThumbnailInfo:
    id: str = strawberry.field()
    source_entity_type: str | None = strawberry.field(default=None)
    source_entity_id: str | None = strawberry.field(default=None)
    relation: str | None = strawberry.field(default=None)


@strawberry.interface
class BaseNode:
    project_name: str = strawberry.field()

    id: str = strawberry.field()

    name: str = strawberry.field(default="")
    active: bool = strawberry.field()
    created_at: datetime = strawberry.field()
    updated_at: datetime = strawberry.field()

    @strawberry.field
    async def links(
        self,
        info: Info,
        direction: str | None = None,
        link_types: list[str] | None = None,
        names: list[str] | None = None,
        name_ex: str | None = None,
        first: int = 100,
        after: str | None = None,
    ) -> LinksConnection:
        resolver = info.context["links_resolver"]
        return await resolver(
            root=self,
            info=info,
            direction=direction,
            link_types=link_types,
            names=names,
            name_ex=name_ex,
            first=first,
            after=after,
        )

    @strawberry.field
    async def activities(
        self,
        info: Info,
        first: int | None = None,
        last: int | None = 100,
        after: str | None = None,
        before: str | None = None,
        activity_types: list[str] | None = None,
        reference_types: list[str] | None = None,
    ) -> ActivitiesConnection:
        resolver = info.context["activities_resolver"]
        return await resolver(
            root=self,
            info=info,
            first=first,
            last=last,
            after=after,
            before=before,
            activity_types=activity_types,
            reference_types=reference_types,
        )

    @strawberry.field()
    def parents(self) -> list[str]:
        return []

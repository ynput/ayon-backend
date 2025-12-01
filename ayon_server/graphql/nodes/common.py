from datetime import datetime
from typing import Any, Optional

import strawberry

from ayon_server.entities import UserEntity
from ayon_server.exceptions import AyonException
from ayon_server.graphql.connections import ActivitiesConnection
from ayon_server.graphql.types import BaseConnection, BaseEdge, Info
from ayon_server.graphql.utils import process_attrib_data
from ayon_server.logging import logger
from ayon_server.utils import json_dumps


@strawberry.type
class ProductType(BaseEdge):
    name: str = strawberry.field()
    icon: str | None = strawberry.field(default=None)
    color: str | None = strawberry.field(default=None)


@strawberry.type
class ProductBaseType(BaseEdge):
    name: str = strawberry.field()


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
    async def node(self, info: Info) -> Optional["BaseNode"]:
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
        if not record:
            return None

        entity_node = await parser(self.project_name, record, info.context)
        access_checker = info.context.get("access_checker")
        if access_checker:
            entity_folder_path = (entity_node._folder_path or "").strip("/")
            if not access_checker[entity_folder_path]:
                # No access to the folder containing the linked entity
                return None
        return entity_node


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
    entity_type: strawberry.Private[str] = "unknown"
    project_name: str = strawberry.field()

    id: str = strawberry.field()

    name: str = strawberry.field(default="")
    active: bool = strawberry.field()

    created_by: str | None = strawberry.field(default=None)
    updated_by: str | None = strawberry.field(default=None)
    created_at: datetime = strawberry.field()
    updated_at: datetime = strawberry.field()

    _attrib: strawberry.Private[dict[str, Any]]
    _user: strawberry.Private[UserEntity]
    _processed_attrib: strawberry.Private[dict[str, Any] | None] = None

    def processed_attrib(self) -> dict[str, Any]:
        if self._processed_attrib is None:
            inherited_attrib = (
                self._inherited_attrib if hasattr(self, "_inherited_attrib") else None
            )
            project_attrib = (
                self._project_attrib if hasattr(self, "_project_attrib") else None
            )
            return process_attrib_data(
                self.entity_type,
                self._attrib,
                user=self._user,
                project_name=self.project_name,
                project_attrib=project_attrib,
                inherited_attrib=inherited_attrib,
            )
        return self._processed_attrib

    @strawberry.field
    def all_attrib(self) -> str:
        return json_dumps(self.processed_attrib())

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

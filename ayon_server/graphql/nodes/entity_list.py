from datetime import datetime
from typing import Any

import strawberry

from ayon_server.entities.user import UserEntity
from ayon_server.exceptions import AyonException, ForbiddenException
from ayon_server.graphql.nodes.common import BaseNode
from ayon_server.graphql.types import BaseConnection, BaseEdge, Info
from ayon_server.graphql.utils import process_attrib_data
from ayon_server.helpers.entity_access import EntityAccessHelper
from ayon_server.logging import logger
from ayon_server.utils import json_dumps

#
# Entity list item
#


@strawberry.type
class EntityListItemEdge(BaseEdge):
    id: str = strawberry.field()
    project_name: str = strawberry.field()

    entity_type: str = strawberry.field()
    entity_id: str = strawberry.field()
    position: int = strawberry.field(default=0)

    attrib: str = strawberry.field(default="{}")
    folder_path: str = strawberry.field(default="")

    tags: list[str] = strawberry.field(default_factory=list)

    created_by: str | None = strawberry.field(default=None)
    updated_by: str | None = strawberry.field(default=None)
    created_at: datetime = strawberry.field(default=None)
    updated_at: datetime = strawberry.field(default=None)

    cursor: str | None = strawberry.field(default=None)

    _entity: BaseNode | BaseNode | None = strawberry.field(default=None)
    _forbidden: bool = strawberry.field(default=False)
    _data: strawberry.Private[dict[str, Any]]
    _attrib: strawberry.Private[dict[str, Any]]  # actual attrib data
    _user: strawberry.Private[UserEntity]

    @strawberry.field()
    def all_attrib(self, info: Info) -> str:
        """All attributes field is a JSON string."""
        if self._entity is None:
            return "{}"

        own_attrib: dict[str, Any] = {}
        inherited_attrib: dict[str, Any] = {}
        project_attrib: dict[str, Any] = {}

        if self._entity:
            if hasattr(self._entity, "_project_attrib"):
                project_attrib = self._entity._project_attrib or {}
            if hasattr(self._entity, "_inherited_attrib"):
                inherited_attrib = self._entity._inherited_attrib or {}
            if hasattr(self._entity, "_attrib"):
                own_attrib = self._entity._attrib or {}

        own_attrib.update(self._attrib or {})

        return json_dumps(
            process_attrib_data(
                self.entity_type,
                own_attrib,
                user=self._user,
                project_name=self.project_name,
                inherited_attrib=inherited_attrib,
                project_attrib=project_attrib,
                list_attribute_config=info.context.get("list_attributes"),
            )
        )

    @strawberry.field()
    def own_attrib(self, info: Info) -> list[str]:
        """Own attributes field is a JSON string."""
        configured_keys = info.context.get("list_attributes") or {}
        return [key for key in self._attrib.keys() if key in configured_keys]

    @strawberry.field()
    def data(self) -> str:
        """Data field is a JSON string."""
        return json_dumps(self._data or {})

    @strawberry.field(description="Item node")
    async def node(self, info: Info) -> "BaseNode | BaseNode | None":
        if self._forbidden:
            return None
        if self._entity:
            return self._entity
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
        else:
            raise AyonException("Unknown entity type in entity list item.")
        record = await loader.load((self.project_name, self.entity_id))
        return await parser(self.project_name, record, info.context)

    @classmethod
    async def from_record(
        cls,
        project_name: str,
        record: dict[str, Any],
        context: dict[str, Any],
    ) -> "EntityListItemEdge":
        entity: BaseNode | BaseNode | None = None
        vdict = {}
        for k, v in record.items():
            if k.startswith("_entity_"):
                k = k.removeprefix("_entity_")
                vdict[k] = v

        if vdict:
            getter_name = f"{context['entity_type']}_from_record"
            if getter := context.get(getter_name):
                # logger.trace(f"Using {getter_name} to get entity")
                entity = await getter(project_name, vdict, context)

        folder_path = record.get("folder_path", "")
        node_access_forbidden = False
        if access_checker := (context or {}).get("access_checker"):
            if folder_path and not access_checker[folder_path]:
                logger.trace(f"Access denied for {folder_path}")
                node_access_forbidden = True

        return cls(
            project_name=project_name,
            id=record["id"],
            entity_type=context["entity_type"],
            entity_id=record["entity_id"],
            position=record["position"],
            folder_path=folder_path,
            tags=record["tags"] or [],
            created_by=record["created_by"],
            updated_by=record["updated_by"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            cursor=record["cursor"],
            _data=record["data"],
            _attrib=record["attrib"],
            _entity=entity,
            _forbidden=node_access_forbidden,
            _user=context["user"],
        )


@strawberry.type
class EntityListItemsConnection(BaseConnection):
    edges: list[EntityListItemEdge] = strawberry.field(default_factory=list)


#
# Entity list
#


@strawberry.type
class EntityListNode:
    project_name: str = strawberry.field()

    id: str = strawberry.field()
    entity_type: str = strawberry.field()
    entity_list_type: str = strawberry.field()
    entity_list_folder_id: str | None = strawberry.field(default=None)
    label: str = strawberry.field()

    access: str = strawberry.field(default="{}")  # JSON string of access dict
    all_attrib: str = strawberry.field(default="{}")  # JSON string of all attrib keys

    tags: list[str] = strawberry.field(default_factory=list)

    owner: str | None = strawberry.field(default=None)
    active: bool = strawberry.field()

    created_at: datetime = strawberry.field()
    updated_at: datetime = strawberry.field()

    created_by: str | None = strawberry.field(default=None)
    updated_by: str | None = strawberry.field(default=None)

    _data: strawberry.Private[dict[str, Any]]
    _access: strawberry.Private[dict[str, Any]]  # access data

    @strawberry.field()
    def count(self) -> int:
        """Count of items in the list."""
        return self._data.get("count", 0)

    @strawberry.field()
    def data(self) -> str:
        """Data field is a JSON string."""
        return json_dumps(self._data or {})

    @strawberry.field()
    def attributes(self) -> str:
        attrs = self._data.get("attributes", [])
        return json_dumps(attrs)

    @strawberry.field
    async def items(
        self,
        info: Info,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
        sort_by: str | None = None,
        accessible_only: bool = False,
        filter: str | None = None,
    ) -> EntityListItemsConnection:
        if first is None and last is None:
            first = 200

        resolver = info.context["entity_list_items_resolver"]
        return await resolver(
            root=self,
            info=info,
            first=first,
            after=after,
            last=last,
            before=before,
            sort_by=sort_by,
            filter=filter,
            accessible_only=accessible_only,
        )

    @strawberry.field
    async def access_level(
        self,
        info: Info,
    ) -> int:
        user = info.context["user"]
        access_level = EntityAccessHelper.MANAGE
        try:
            await EntityAccessHelper.check(
                user,
                access=self._access,
                level=EntityAccessHelper.MANAGE,
                owner=self.owner,
                project=info.context.get("project"),
                default_open=True,
            )
        except ForbiddenException as e:
            access_level = e.extra.get("access_level", 10)
        return access_level


async def entity_list_from_record(
    project_name: str,
    record: dict[str, Any],
    context: dict[str, Any],
) -> EntityListNode:
    data = record.get("data", {})
    user = context.get("user")

    entity_list_folder_id = record.get("entity_list_folder_id")

    if user:
        await EntityAccessHelper.check(
            user,
            access=record.get("access"),
            level=EntityAccessHelper.READ,
            owner=record.get("owner"),
            project=context.get("project"),
            default_open=True,
        )

    return EntityListNode(
        project_name=project_name,
        id=record["id"],
        entity_list_type=record["entity_list_type"],
        entity_list_folder_id=entity_list_folder_id,
        entity_type=record["entity_type"],
        label=record["label"],
        access=json_dumps(record.get("access") or {}),
        all_attrib=json_dumps(record.get("attrib") or {}),
        tags=record["tags"] or [],
        owner=record["owner"],
        active=record["active"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        created_by=record["created_by"],
        updated_by=record["updated_by"],
        _data=data,
        _access=record.get("access") or {},
    )


EntityListNode.from_record = entity_list_from_record  # type: ignore

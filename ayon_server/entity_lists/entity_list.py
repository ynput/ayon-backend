from typing import Any

from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import (
    ForbiddenException,
    NotFoundException,
    NotImplementedException,
)
from ayon_server.helpers.entity_access import EntityAccessHelper
from ayon_server.lib.postgres import Postgres
from ayon_server.types import ProjectLevelEntityType
from ayon_server.utils import create_uuid, now
from ayon_server.utils.utils import dict_patch

from .entity_folder_path import get_entity_folder_path
from .models import (
    EntityListItemModel,
    EntityListModel,
    EntityListSummary,
    ListAccessLevel,
)
from .save_entity_list import save_entity_list


class EntityList:
    _project_name: str
    _payload: EntityListModel
    _user: UserEntity | None

    def __init__(
        self,
        project_name: str,
        payload: EntityListModel,
        *,
        user: UserEntity | None = None,
        conn: Any = None,  # deprecated
    ):
        self._project_name = project_name
        self._payload = payload
        self._user = user

    @property
    def id(self) -> str:
        return self._payload.id

    @property
    def project_name(self) -> str:
        return self._project_name

    @property
    def payload(self) -> EntityListModel:
        return self._payload

    @property
    def items(self) -> list[EntityListItemModel]:
        return self._payload.items

    @property
    def entity_type(self) -> ProjectLevelEntityType:
        return self._payload.entity_type

    @property
    def entity_list_type(self) -> str:
        return self._payload.entity_list_type

    @property
    def entity_list_folder_id(self) -> str | None:
        return self._payload.entity_list_folder_id

    async def ensure_access_level(
        self,
        user: UserEntity | None = None,
        level: int = 0,
        default_open: bool = True,
    ) -> None:
        _user = user or self._user
        if not _user:
            return

        await EntityAccessHelper.check(
            _user,
            access=self._payload.access,
            level=level,
            owner=self._payload.owner,
            default_open=default_open,
        )

    async def ensure_can_read(self, user: UserEntity | None = None) -> None:
        _user = user or self._user
        """Check if the user has permission to read the entity list."""
        try:
            await self.ensure_access_level(user=user, level=10)
        except ForbiddenException as e:
            assert _user, "this should not happen"
            raise ForbiddenException(
                f"Cannot read entity list {self._payload.label}"
            ) from e

    async def ensure_can_update(self, user: UserEntity | None = None) -> None:
        """Check if the user has permission to update the entity list."""
        try:
            await self.ensure_access_level(user=user, level=20)
        except ForbiddenException as e:
            raise ForbiddenException(
                f"Cannot update entity list {self._payload.label}"
            ) from e

    async def ensure_can_admin(self, user: UserEntity | None = None) -> None:
        """Check if the user has permission to admin the entity list."""
        try:
            await self.ensure_access_level(user=user, level=30)
        except ForbiddenException as e:
            raise ForbiddenException(
                f"Cannot admin entity list {self._payload.label}"
            ) from e

    @classmethod
    async def construct(
        cls,
        project_name: str,
        entity_type: ProjectLevelEntityType,
        label: str,
        *,
        id: str | None = None,
        entity_list_type: str = "generic",
        entity_list_folder_id: str | None = None,
        template: dict[str, Any] | None = None,
        access: dict[str, Any] | None = None,
        attrib: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        active: bool = True,
        owner: str | None = None,
        created_by: str | None = None,
        updated_by: str | None = None,
        user: UserEntity | None = None,
        conn: Any = None,  # deprecated
    ) -> "EntityList":
        if user:
            owner = owner or user.name
            created_by = created_by or user.name
            updated_by = updated_by or user.name

        payload = EntityListModel(
            id=id or create_uuid(),
            entity_type=entity_type,
            entity_list_type=entity_list_type,
            entity_list_folder_id=entity_list_folder_id,
            label=label,
            tags=tags or [],
            attrib=attrib or {},
            data=data or {},
            access=access or {},
            template=template or {},
            owner=owner,
            created_by=created_by,
            updated_by=updated_by,
            active=active,
            items=[],
            created_at=now(),
            updated_at=now(),
        )

        res = cls(project_name, payload, user=user)
        return res

    @classmethod
    async def load(
        cls,
        project_name: str,
        id: str,
        user: UserEntity | None = None,
        with_items: bool = True,
        conn: Any = None,  # deprecated
    ) -> "EntityList":
        """Load the entity list from the database."""

        async with Postgres.transaction():
            await Postgres.execute(f"SET LOCAL search_path TO project_{project_name}")
            query = "SELECT * FROM entity_lists WHERE id = $1"
            res = await Postgres.fetchrow(query, id)
            if not res:
                raise NotFoundException(f"Entity list {id} not found")
            items = []

            if with_items:
                item_query = """
                    SELECT * FROM entity_list_items
                    WHERE entity_list_id = $1 ORDER BY position
                """

                stmt = await Postgres.prepare(item_query)
                async for row in stmt.cursor(res["id"]):
                    item = EntityListItemModel(**row)
                    items.append(item)

        access_level = EntityAccessHelper.MANAGE
        if user:
            project = await ProjectEntity.load(project_name)
            access_level = EntityAccessHelper.MANAGE
            try:
                await EntityAccessHelper.check(
                    user,
                    access=res["access"],
                    level=access_level,
                    owner=res["owner"],
                    project=project,
                    default_open=True,
                )
            except ForbiddenException as e:
                access_level = e.extra.get("access_level", 10)
            if access_level < 10:
                raise ForbiddenException(f"Access denied to entity list {res['label']}")

        return cls(
            project_name,
            EntityListModel(
                **res,
                access_level=ListAccessLevel(access_level),
                items=items,
            ),
            user=user,
        )

    def item_by_id(self, item_id: str) -> EntityListItemModel:
        """Get an item by ID"""
        for item in self._payload.items:
            if item.id == item_id:
                return item
        raise NotFoundException(f"Item ID {item_id} not found in {self._payload.label}")

    def normalize_positions(self) -> None:
        """Normalize the positions of all items in the list"""
        for i, item in enumerate(self._payload.items):
            item.position = i

    async def add(
        self,
        entity_id: str,
        *,
        id: str | None = None,
        position: int | None = None,
        label: str | None = None,
        attrib: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        normalize_positions: bool = True,
    ) -> str:
        """Add an item to the list, returning the item ID"""

        folder_path = await get_entity_folder_path(
            self._project_name,
            self._payload.entity_type,
            entity_id,
        )

        item = EntityListItemModel(
            id=id or create_uuid(),
            entity_id=entity_id,
            position=position or 99999999,
            label=label,
            attrib=attrib or {},
            data=data or {},
            tags=tags or [],
            created_at=now(),
            updated_at=now(),
            folder_path=folder_path,
            created_by=self._user.name if self._user else None,
            updated_by=self._user.name if self._user else None,
        )

        if position is not None:
            self._payload.items.insert(position, item)
        else:
            self._payload.items.append(item)

        if normalize_positions:
            self.normalize_positions()
        return item.id

    async def update(
        self,
        item_id: str,
        *,
        entity_id: str | None = None,
        position: int | None = None,
        label: str | None = None,
        attrib: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        merge_fields: bool = False,
        normalize_positions: bool = True,
    ) -> None:
        """Update an item in the list"""

        item = self.item_by_id(item_id)
        if entity_id is not None:
            if entity_id != item.entity_id:
                item.entity_id = entity_id
                item.folder_path = await get_entity_folder_path(
                    self._project_name,
                    self._payload.entity_type,
                    entity_id,
                )
        if position is not None:
            if position != item.position:
                item.position = position
                if normalize_positions:
                    self.normalize_positions()

        if label is not None:
            item.label = label
        if attrib is not None:
            if merge_fields:
                item.attrib = dict_patch(item.attrib, attrib)
            else:
                item.attrib = attrib
        if data is not None:
            if merge_fields:
                item.data = dict_patch(item.data, data)
            else:
                item.data = data
        if tags is not None:
            # Tags are always replaced, not merged
            item.tags = tags

    async def remove(self, item_id: str) -> None:
        """Remove an item from the list"""
        for i, item in enumerate(self._payload.items):
            if item.id == item_id:
                del self._payload.items[i]
                self.normalize_positions()
                return
        raise NotFoundException(f"Item ID {item_id} not found in {self._payload.label}")

    async def save(
        self,
        *,
        user: UserEntity | None = None,
        sender: str | None = None,
        sender_type: str | None = None,
    ) -> EntityListSummary:
        """Save the entity list to the database"""
        _user = user or self._user
        return await save_entity_list(
            self._project_name,
            self._payload,
            user=_user,
            sender=sender,
            sender_type=sender_type,
        )

    async def delete(
        self,
        *,
        user: UserEntity | None = None,
        sender: str | None = None,
        sender_type: str | None = None,
    ) -> None:
        _user = user or self._user

        summary = {
            "id": self._payload.id,
            "entity_list_type": self._payload.entity_list_type,
            "entity_list_folder_id": self._payload.entity_list_folder_id,
            "entity_type": self._payload.entity_type,
            "label": self._payload.label,
            "count": len(self._payload.items),
        }

        query = f"""
            DELETE FROM project_{self._project_name}.entity_lists
            WHERE id = $1
        """

        await Postgres.execute(query, self._payload.id)

        await EventStream.dispatch(
            "entity_list.deleted",
            summary=summary,
            description=f"Deleted entity list {self._payload.label}",
            project=self._project_name,
            user=_user.name if _user else None,
            sender=sender,
            sender_type=sender_type,
        )

    async def materialize(self) -> None:
        """Materialize the entity list"""

        raise NotImplementedException("Materialize entity list is not implemented yet")

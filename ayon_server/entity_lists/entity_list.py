"""This class is experimental. Not to be used yet"""

from typing import Any

from ayon_server.entities import UserEntity
from ayon_server.lib.postgres import Connection
from ayon_server.types import ProjectLevelEntityType
from ayon_server.utils import create_uuid, now

from .entity_folder_path import get_entity_folder_path
from .load_entity_list import load_entity_list
from .models import EntityListItemModel, EntityListModel
from .save_entity_list import save_entity_list


class EntityList:
    _project_name: str
    _payload: EntityListModel
    _user: UserEntity | None
    _connection: Connection | None

    def __init__(
        self,
        project_name: str,
        payload: EntityListModel,
    ):
        self._project_name = project_name
        self._payload = payload

    @property
    def id(self) -> str:
        return self._payload.id

    @property
    def project_name(self) -> str:
        return self._project_name

    @classmethod
    async def construct(
        cls,
        project_name: str,
        entity_type: ProjectLevelEntityType,
        label: str,
        *,
        entity_list_type: str = "generic",
        id: str | None = None,
        access: dict[str, Any] | None = None,
        template: dict[str, Any] | None = None,
        attrib: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        active: bool = True,
        user: UserEntity | None = None,
        owner: str | None = None,
        created_by: str | None = None,
        updated_by: str | None = None,
    ) -> "EntityList":
        if user:
            owner = owner or user.name
            created_by = created_by or user.name
            updated_by = updated_by or user.name

        payload = EntityListModel(
            id=id or create_uuid(),
            entity_type=entity_type,
            entity_list_type=entity_list_type,
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

        res = cls(project_name, payload)
        res._user = user
        return res

    @classmethod
    async def load(cls, project_name: str, id: str) -> "EntityList":
        """Load the entity list from the database."""
        payload = await load_entity_list(project_name, id)
        return cls(project_name, payload)

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
    ) -> None:
        """Add an item to the list"""

        folder_path = await get_entity_folder_path(
            self._project_name,
            self._payload.entity_type,
            entity_id,
        )

        item = EntityListItemModel(
            id=id or create_uuid(),
            entity_id=entity_id,
            position=position or 0,
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

        if position:
            self._payload.items.insert(position, item)
        else:
            self._payload.items.append(item)

        # normalize positions of all items
        for i, item in enumerate(self._payload.items):
            item.position = i

    async def save(self) -> None:
        """Save the entity list to the database"""
        await save_entity_list(self._project_name, self._payload)

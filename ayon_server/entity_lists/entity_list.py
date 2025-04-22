"""This class is experimental. Not to be used yet"""

from typing import Any

from ayon_server.entities import UserEntity
from ayon_server.lib.postgres import Connection, Postgres
from ayon_server.types import ProjectLevelEntityType
from ayon_server.utils import create_uuid

from .models import EntityListModel


class EntityList:
    _project_name: str
    _payload: EntityListModel
    _conn: Connection | None

    def __init__(
        self,
        project_name: str,
        payload: EntityListModel,
        conn: Connection | None = None,
    ):
        self._project_name = project_name
        self._payload = payload
        self._conn = conn

    @property
    def id(self) -> str:
        return self._payload.id

    @property
    def project_name(self) -> str:
        return self._project_name

    @classmethod
    async def create(
        cls,
        project_name: str,
        entity_type: ProjectLevelEntityType,
        label: str,
        *,
        id: str | None = None,
        entity_list_type: str | None = None,
        tags: list[str] | None = None,
        attrib: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        access: dict[str, Any] | None = None,
        template: dict[str, Any] | None = None,
        user: UserEntity | None = None,
        sender: str | None = None,
        sender_type: str | None = None,
        conn: Connection | None = None,
    ) -> "EntityList":
        user_name = user.name if user else None

        payload = EntityListModel(
            id=id or create_uuid(),
            entity_type=entity_type,
            entity_list_type=entity_list_type or "generic",
            label=label,
            tags=tags or [],
            attrib=attrib or {},
            data=data or {},
            access=access or {},
            template=template or {},
            owner=user_name,
            created_by=user_name,
            updated_by=user_name,
        )

        async def execute_insert(conn: Connection):
            keys: list[str] = []
            placeholders: list[str] = []
            values: list[Any] = []

            i = 0
            for key, value in payload.dict().items():
                i += 1
                keys.append(key)
                placeholders.append(f"${i}")
                values.append(value)

            query = f"""
            INSERT INTO entity_lists ({', '.join(keys)})
            VALUES ({', '.join(placeholders)})
            """
            await conn.execute(f"SET LOCAL search_path TO {project_name}")
            await conn.execute(query, *values)

        if conn is not None:
            await execute_insert(conn)
            return cls(project_name, payload, conn)
        else:
            async with Postgres.acquire() as conn, conn.transaction():
                await execute_insert(conn)
                return cls(project_name, payload, conn)
